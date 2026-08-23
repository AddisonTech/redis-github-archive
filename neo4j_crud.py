"""
neo4j_crud.py

CRUD operations on commit nodes stored in Neo4j. This is the Neo4j
counterpart to crud_operations.py (Redis), mongo_crud.py (MongoDB), and
cassandra_crud.py (Cassandra).

The commit hash is the unique property on the Commit node, backed by the
constraint applied in neo4j_config.py, so every operation here is an
index lookup rather than a scan.

What is different from the earlier three parts
----------------------------------------------
A record in this database is not a self-contained row or document. A
commit is a node sitting in the middle of relationships to an author, a
repository, and the files it touched, and those relationships are the
data. That changes both ends of the CRUD lifecycle.

Creating a commit is not one write. It has to attach the commit to an
author node and a repo node, creating either if it does not already
exist, which is what MERGE does in a single statement.

Deleting a commit has to remove its relationships as well, or Neo4j
refuses the delete outright rather than leaving a dangling edge. This is
enforced by the database, which is a real difference from the earlier
parts: Redis and Cassandra both allowed orphaned index entries and left
the cleanup as the application's problem. DETACH DELETE handles it in
one operation.
"""

from neo4j_config import get_session

# Properties on a Commit node that the update path is allowed to touch.
# The hash is excluded because it is the identifier the constraint is
# built on; changing it would be a delete and a create, not an update.
UPDATABLE_FIELDS = {"subject", "message", "num_files_changed"}


def create_record(session, commit_hash, repo_name, author_name, subject,
                  message=""):
    """
    Creates a commit node and wires it to its author and repository,
    creating either of those if they do not already exist. Returns
    False if a commit with that hash is already in the graph.

    The existence check is separate rather than folded into a MERGE,
    because MERGE on an existing hash would quietly match the existing
    node and overwrite its properties instead of reporting a conflict.
    """
    existing = session.run(
        "MATCH (c:Commit {hash: $hash}) RETURN c.hash AS hash",
        hash=commit_hash).single()
    if existing:
        return False

    session.run("""
        MERGE (a:Author {name: $author_name})
        MERGE (r:Repo {name: $repo_name})
        CREATE (c:Commit {
            hash: $hash,
            subject: $subject,
            message: $message,
            num_files_changed: 0
        })
        MERGE (a)-[:AUTHORED]->(c)
        MERGE (c)-[:IN_REPO]->(r)
        MERGE (a)-[rel:CONTRIBUTED_TO]->(r)
          ON CREATE SET rel.commits = 1
          ON MATCH SET rel.commits = rel.commits + 1
    """, hash=commit_hash, repo_name=repo_name, author_name=author_name,
         subject=subject, message=message)

    return True


def read_record(session, commit_hash):
    """
    Returns one commit along with its author, repository, and the files
    it modified, or None if the hash is not in the graph.

    A single query returns the node and everything attached to it. The
    equivalent in the document and column-family parts either lived in
    one record already or required separate lookups; here the joins are
    the traversal.
    """
    result = session.run("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit {hash: $hash})-[:IN_REPO]->(r:Repo)
        OPTIONAL MATCH (c)-[:MODIFIED]->(f:File)
        RETURN c.hash AS hash,
               c.subject AS subject,
               c.message AS message,
               c.num_files_changed AS num_files_changed,
               a.name AS author_name,
               a.email AS author_email,
               r.name AS repo_name,
               collect(f.path) AS files
    """, hash=commit_hash).single()

    return dict(result) if result else None


def update_record(session, commit_hash, field, value):
    """
    Updates a single property on an existing commit. Returns False if
    the commit does not exist, and None if the field name is not one
    the application allows to be changed.

    Property names cannot be parameterized in Cypher, the same
    restriction CQL has on column names, so the field is validated
    against a fixed allowlist before it is formatted into the statement.
    """
    if field not in UPDATABLE_FIELDS:
        return None

    if field == "num_files_changed":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None

    result = session.run(
        f"MATCH (c:Commit {{hash: $hash}}) "
        f"SET c.{field} = $value "
        f"RETURN c.hash AS hash",
        hash=commit_hash, value=value).single()

    return result is not None


def delete_record(session, commit_hash):
    """
    Deletes a commit and every relationship attached to it, and
    decrements the author's contribution weight for that repository.

    DETACH DELETE removes the relationships and the node together.
    Without DETACH, Neo4j raises an error rather than allowing a node
    with edges to be deleted, which is the database refusing to let the
    graph become inconsistent. Redis and Cassandra both permitted the
    equivalent inconsistency and left it to the application to prevent.

    The contribution edge is a derived roll-up rather than a structural
    relationship, so it is adjusted rather than deleted, and it is
    removed entirely once its weight reaches zero.
    """
    exists = session.run(
        "MATCH (c:Commit {hash: $hash}) RETURN c.hash AS hash",
        hash=commit_hash).single()
    if not exists:
        return False

    session.run("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit {hash: $hash})-[:IN_REPO]->(r:Repo)
        MATCH (a)-[rel:CONTRIBUTED_TO]->(r)
        SET rel.commits = rel.commits - 1
        WITH rel
        WHERE rel.commits <= 0
        DELETE rel
    """, hash=commit_hash)

    session.run("MATCH (c:Commit {hash: $hash}) DETACH DELETE c",
                hash=commit_hash)

    return True


def search_by_author(session, author_name, limit=10):
    """
    Finds commits by an author using a case-insensitive match, returning
    the commit alongside the repository it belongs to.

    Every part of this project implements this differently and the
    differences are informative. MongoDB used a regex query over a
    field. Cassandra could not do it at all without a table built for
    that access pattern in advance. Here it is a pattern match: find
    the author node, then walk its AUTHORED edges.
    """
    result = session.run("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:IN_REPO]->(r:Repo)
        WHERE toLower(a.name) CONTAINS toLower($author_name)
        RETURN c.hash AS hash, a.name AS author_name,
               r.name AS repo_name, c.subject AS subject
        LIMIT $limit
    """, author_name=author_name, limit=limit)

    return [dict(record) for record in result]


def list_loaded_repos(session, limit=25):
    """
    Returns repository names that have commit data in the graph, so the
    menus can show the user valid choices.
    """
    result = session.run("""
        MATCH (:Commit)-[:IN_REPO]->(r:Repo)
        RETURN DISTINCT r.name AS name
        ORDER BY name
        LIMIT $limit
    """, limit=limit)
    return [record["name"] for record in result]


def run_crud_menu():
    """
    Text menu exercising all four CRUD operations plus author search
    against the graph.
    """
    with get_session() as session:
        while True:
            print("\n1. Create  2. Read  3. Update  4. Delete  "
                  "5. Search by author  6. Back to Main Menu")
            choice = input("Choose an option: ").strip()

            if choice == "1":
                commit_hash = input("New commit hash (any unique string): ").strip()
                repo_name = input("Repo name: ").strip()
                author_name = input("Author name: ").strip()
                subject = input("Commit subject: ").strip()
                if not commit_hash or not repo_name or not author_name:
                    print("Commit hash, repo name, and author name are required.")
                elif create_record(session, commit_hash, repo_name,
                                   author_name, subject):
                    print("Commit created and linked to its author and repo.")
                else:
                    print("A commit with that hash already exists.")

            elif choice == "2":
                commit_hash = input("Commit hash to look up: ").strip()
                record = read_record(session, commit_hash)
                if record:
                    for field, value in record.items():
                        if field == "files":
                            shown = [p for p in value if p]
                            print(f"  files: {len(shown)} file(s)")
                            for path in shown[:10]:
                                print(f"    {path}")
                        else:
                            print(f"  {field}: {value}")
                else:
                    print("No commit found with that hash.")

            elif choice == "3":
                commit_hash = input("Commit hash to update: ").strip()
                field = input("Field to update (subject, message, "
                              "num_files_changed): ").strip()
                value = input("New value: ").strip()
                result = update_record(session, commit_hash, field, value)
                if result is None:
                    print("That field cannot be updated. Try subject, "
                          "message, or num_files_changed.")
                elif result:
                    print("Commit updated.")
                else:
                    print("No commit found with that hash.")

            elif choice == "4":
                commit_hash = input("Commit hash to delete: ").strip()
                if delete_record(session, commit_hash):
                    print("Commit and its relationships deleted.")
                else:
                    print("No commit found with that hash.")

            elif choice == "5":
                author_name = input("Author name to search for: ").strip()
                results = search_by_author(session, author_name)
                if not results:
                    print("No commits found for that author.")
                else:
                    print(f"\nFound {len(results)} commit(s):")
                    for record in results:
                        print(f"  [{record['hash'][:10]}] "
                              f"{record['repo_name']}: "
                              f"{(record['subject'] or '')[:50]}")

            elif choice == "6":
                break
            else:
                print("Not a valid option, try again.")


if __name__ == "__main__":
    run_crud_menu()
