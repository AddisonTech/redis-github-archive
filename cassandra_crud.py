"""
cassandra_crud.py

CRUD operations on commit records stored in Cassandra. This is the
Cassandra counterpart to crud_operations.py (Redis) and mongo_crud.py
(MongoDB).

The commit hash is the partition key of commits_by_hash, so every
single-record operation here is a direct partition lookup, which is the
access pattern Cassandra is built around.

Two behaviors here differ from the MongoDB version and are worth calling
out, because they are the practical cost of Cassandra's write path:

Writes are upserts. An INSERT against an existing partition key
silently overwrites it, so creating a record that already exists needs
an explicit read first, or a lightweight transaction using IF NOT
EXISTS. This module uses IF NOT EXISTS, which makes the check atomic
rather than leaving a gap between the read and the write.

Denormalized copies have to be maintained by hand. A commit lives in
commits_by_hash and commits_by_repo, and its author has a counter in
commit_counts_by_author, so a delete has to touch all three or the
extra tables are left holding rows that no longer exist. This is the
same class of work the Redis version had to do with its set and sorted
set indexes, and the opposite of MongoDB where a delete is one call.
"""

from cassandra.query import BatchStatement, ConsistencyLevel
from cassandra_config import get_session, GLOBAL_BUCKET


def create_record(session, commit_hash, repo_name, author_name, subject,
                  message=""):
    """
    Inserts a new commit and its denormalized copy, then increments the
    author counter. Returns False if a commit with that hash already
    exists.

    IF NOT EXISTS makes this a lightweight transaction, which uses Paxos
    behind the scenes and is noticeably slower than a plain write. That
    is acceptable for a single user-entered record and would not be
    acceptable inside the bulk loader.
    """
    result = session.execute("""
        INSERT INTO commits_by_hash (
            commit_hash, repo_name, author_name, author_email,
            committer_name, subject, message, tree,
            files_changed, num_files_changed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        IF NOT EXISTS
    """, (commit_hash, repo_name, author_name, "", author_name, subject,
          message, "", [], 0))

    # A lightweight transaction returns a row with an [applied] column
    # telling you whether the write actually happened.
    if not result.one().applied:
        return False

    session.execute("""
        INSERT INTO commits_by_repo (
            repo_name, commit_hash, author_name, subject, num_files_changed)
        VALUES (%s, %s, %s, %s, %s)
    """, (repo_name, commit_hash, author_name, subject, 0))

    session.execute("""
        UPDATE commit_counts_by_author
        SET commit_count = commit_count + 1
        WHERE repo_name = %s AND author_name = %s
    """, (repo_name, author_name))

    session.execute(
        "INSERT INTO repos_loaded (bucket, repo_name) VALUES (%s, %s)",
        (GLOBAL_BUCKET, repo_name))

    return True


def read_record(session, commit_hash):
    """
    Returns one commit row by its hash, or None if it does not exist.
    """
    result = session.execute(
        "SELECT * FROM commits_by_hash WHERE commit_hash = %s",
        (commit_hash,))
    return result.one()


def update_record(session, commit_hash, field, value):
    """
    Updates a single field on an existing commit. Returns False if the
    commit does not exist.

    The existence check is explicit because Cassandra treats an UPDATE
    on a missing partition key as an insert. Without the check, updating
    a typo'd hash would quietly create a half-empty row.

    Column names cannot be bound as parameters in CQL, so the field name
    is validated against a fixed allowlist before it is formatted into
    the statement. That keeps a user-supplied string from ever reaching
    the query as raw CQL.
    """
    allowed_fields = {
        "repo_name", "author_name", "author_email", "committer_name",
        "subject", "message", "tree", "num_files_changed",
    }
    if field not in allowed_fields:
        return None  # signals an invalid field name rather than a miss

    existing = read_record(session, commit_hash)
    if existing is None:
        return False

    if field == "num_files_changed":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None

    session.execute(
        f"UPDATE commits_by_hash SET {field} = %s WHERE commit_hash = %s",
        (value, commit_hash))

    # Keep the denormalized copy in step for the fields it also stores.
    if field in ("author_name", "subject", "num_files_changed"):
        session.execute(
            f"UPDATE commits_by_repo SET {field} = %s "
            f"WHERE repo_name = %s AND commit_hash = %s",
            (value, existing.repo_name, commit_hash))

    return True


def delete_record(session, commit_hash):
    """
    Deletes a commit from both commit tables and decrements the author
    counter so the analysis features stay accurate. Returns False if
    the commit did not exist.

    The two deletes are sent as a logged batch. A logged batch in
    Cassandra is not a transaction and gives no isolation, but it does
    guarantee that if the first statement is applied the second one
    eventually will be, which is exactly what keeping two copies of the
    same row in step requires. The counter decrement stays outside the
    batch, since counter and non-counter statements cannot be mixed.
    """
    record = read_record(session, commit_hash)
    if record is None:
        return False

    batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)
    batch.add("DELETE FROM commits_by_hash WHERE commit_hash = %s",
              (commit_hash,))
    batch.add("DELETE FROM commits_by_repo "
              "WHERE repo_name = %s AND commit_hash = %s",
              (record.repo_name, commit_hash))
    session.execute(batch)

    session.execute("""
        UPDATE commit_counts_by_author
        SET commit_count = commit_count - 1
        WHERE repo_name = %s AND author_name = %s
    """, (record.repo_name, record.author_name))

    return True


def list_commits_by_repo(session, repo_name, limit=10):
    """
    Returns commits belonging to one repository. This reads
    commits_by_repo rather than commits_by_hash, which is the whole
    reason that second table exists.

    Running the same query against commits_by_hash would require
    ALLOW FILTERING, which tells Cassandra to read every partition in
    the cluster and throw away what does not match. It works on a lab
    dataset and falls over on a real one, so the table layout avoids
    needing it at all.
    """
    result = session.execute(
        "SELECT commit_hash, author_name, subject, num_files_changed "
        "FROM commits_by_repo WHERE repo_name = %s LIMIT %s",
        (repo_name, limit))
    return list(result)


def list_loaded_repos(session):
    """
    Returns the repository names that have commit data loaded, so the
    menus can show the user valid choices.
    """
    result = session.execute(
        "SELECT repo_name FROM repos_loaded WHERE bucket = %s",
        (GLOBAL_BUCKET,))
    return sorted(row.repo_name for row in result)


def run_crud_menu():
    """
    Text menu exercising all four CRUD operations plus a per-repository
    listing against the Cassandra tables.
    """
    session = get_session()

    while True:
        print("\n1. Create  2. Read  3. Update  4. Delete  "
              "5. List commits by repo  6. Back to Main Menu")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            commit_hash = input("New commit hash (any unique string): ").strip()
            repo_name = input("Repo name: ").strip()
            author_name = input("Author name: ").strip()
            subject = input("Commit subject: ").strip()
            if not commit_hash or not repo_name or not author_name:
                print("Commit hash, repo name, and author name are required.")
            elif create_record(session, commit_hash, repo_name, author_name,
                               subject):
                print("Commit created.")
            else:
                print("A commit with that hash already exists.")

        elif choice == "2":
            commit_hash = input("Commit hash to look up: ").strip()
            row = read_record(session, commit_hash)
            if row:
                for field in row._fields:
                    print(f"  {field}: {getattr(row, field)}")
            else:
                print("No commit found with that hash.")

        elif choice == "3":
            commit_hash = input("Commit hash to update: ").strip()
            field = input("Field to update (e.g. subject): ").strip()
            value = input("New value: ").strip()
            result = update_record(session, commit_hash, field, value)
            if result is None:
                print("That field cannot be updated. Try subject, message, "
                      "author_name, author_email, committer_name, or tree.")
            elif result:
                print("Commit updated.")
            else:
                print("No commit found with that hash.")

        elif choice == "4":
            commit_hash = input("Commit hash to delete: ").strip()
            if delete_record(session, commit_hash):
                print("Commit deleted.")
            else:
                print("No commit found with that hash.")

        elif choice == "5":
            repos = list_loaded_repos(session)
            print("Available repos:", ", ".join(repos) if repos
                  else "none loaded yet")
            if repos:
                repo_name = input("Enter a repo name from the list: ").strip()
                rows = list_commits_by_repo(session, repo_name)
                if not rows:
                    print("No commits found for that repository.")
                for row in rows:
                    print(f"  [{row.commit_hash[:10]}] "
                          f"{row.author_name[:20]:<20} "
                          f"{(row.subject or '')[:50]}")

        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    run_crud_menu()
