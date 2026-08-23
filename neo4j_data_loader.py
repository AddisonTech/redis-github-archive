"""
neo4j_data_loader.py

Loads the GitHub Archive dataset into Neo4j as a property graph. This is
the Neo4j counterpart to the loaders in parts 1 through 3.

The graph model
---------------
    (:Author {name, email})
    (:Commit {hash, subject, message, num_files_changed})
    (:Repo   {name, watch_count})
    (:File   {path})
    (:License {name})

    (Author)-[:AUTHORED]->(Commit)
    (Commit)-[:IN_REPO]->(Repo)
    (Commit)-[:MODIFIED]->(File)
    (Repo)-[:LICENSED_UNDER]->(License)
    (Author)-[:CONTRIBUTED_TO {commits: n}]->(Repo)

The first four relationships come straight out of the source data. The
fifth is derived after loading, by rolling up each author's commits per
repository into a single weighted edge.

That derived relationship is the interesting design decision in this
part. The same information is already reachable by walking
Author -> Commit -> Repo, so it is technically redundant, which is the
kind of thing a relational schema would forbid. In a graph database it
is the standard move: the collaboration and similarity features
traverse author-to-repo constantly, and collapsing thousands of commit
hops into one edge turns those traversals from expensive into trivial.
It is the graph equivalent of the denormalization the Cassandra part
did by storing each commit in two tables, done for the same reason and
with the same trade, which is that the derived edge has to be rebuilt
when the underlying data changes.

Why the writes look the way they do
-----------------------------------
Every write goes through UNWIND over a batch parameter rather than one
statement per record. Sending a list of rows into a single Cypher
statement means one round trip and one query plan for the whole batch
instead of one of each per row. Combined with the uniqueness constraints
that neo4j_config.py applies before any data is written, this is the
difference between a load that finishes and one that does not.
"""

import json
import os
from neo4j_config import get_session

# Rows per transaction. Large enough to amortize the round trip, small
# enough that a single transaction's memory footprint stays reasonable.
BATCH_SIZE = 2000


def _stream_json_lines(filepath):
    """
    Yields one parsed record per line from a newline-delimited JSON
    file, skipping blanks and anything that fails to parse. Generator
    rather than a list so the whole file never sits in memory.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def clear_graph(session):
    """
    Deletes every node and relationship so a reload starts clean.

    This runs in chunks rather than as a single DETACH DELETE over the
    whole graph. Neo4j holds a transaction in memory until it commits,
    so deleting several hundred thousand nodes in one transaction is a
    reliable way to exhaust the heap. CALL ... IN TRANSACTIONS commits
    as it goes.
    """
    print("Clearing existing graph...")
    session.run("""
        MATCH (n)
        CALL { WITH n DETACH DELETE n }
        IN TRANSACTIONS OF 10000 ROWS
    """)


def load_commits(session, filepath, max_files_per_commit=25):
    """
    Loads Sample_Commits.json, creating the Author, Commit, Repo, and
    File nodes along with the relationships between them.

    max_files_per_commit caps how many File nodes a single commit
    contributes. A handful of commits in this dataset touch thousands
    of files, and those alone would produce more File nodes than the
    rest of the dataset combined without changing what any feature
    reports.
    """
    query = """
    UNWIND $rows AS row
    MERGE (c:Commit {hash: row.hash})
      SET c.subject = row.subject,
          c.message = row.message,
          c.num_files_changed = row.num_files_changed
    MERGE (a:Author {name: row.author_name})
      SET a.email = row.author_email
    MERGE (r:Repo {name: row.repo_name})
    MERGE (a)-[:AUTHORED]->(c)
    MERGE (c)-[:IN_REPO]->(r)
    WITH c, row
    UNWIND row.files AS file_path
      MERGE (f:File {path: file_path})
      MERGE (c)-[:MODIFIED]->(f)
    """

    batch = []
    count = 0

    for record in _stream_json_lines(filepath):
        commit_hash = record.get("commit")
        repo_name = record.get("repo_name")
        if not commit_hash or not repo_name:
            continue

        author = record.get("author") or {}
        difference = record.get("difference") or []
        files = [d.get("new_path") for d in difference if d.get("new_path")]

        batch.append({
            "hash": commit_hash,
            "repo_name": repo_name,
            "author_name": author.get("name", "unknown"),
            "author_email": author.get("email", ""),
            "subject": record.get("subject", ""),
            "message": record.get("message", ""),
            "num_files_changed": len(difference),
            # Empty list is fine: UNWIND over an empty list produces no
            # rows, so a commit with no file data simply skips that part.
            "files": files[:max_files_per_commit],
        })

        count += 1
        if len(batch) >= BATCH_SIZE:
            session.run(query, rows=batch)
            batch = []
            print(f"  ...{count:,} commits loaded")

    if batch:
        session.run(query, rows=batch)

    print(f"Loaded {count:,} commits.")
    return count


def load_repos(session, filepath):
    """
    Loads Sample_Repos.json, setting watch_count on Repo nodes.

    MERGE rather than CREATE, because load_commits has already created
    Repo nodes for the repositories that have commit data. Those nodes
    get their watch count filled in here; repositories that appear only
    in this file are created fresh.

    watch_count arrives as a string in the source data and is converted
    to an integer here, since the features sort on it numerically.
    """
    query = """
    UNWIND $rows AS row
    MERGE (r:Repo {name: row.repo_name})
      SET r.watch_count = row.watch_count
    """

    batch = []
    count = 0

    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        if not repo_name:
            continue
        try:
            watch_count = int(record.get("watch_count", 0))
        except (TypeError, ValueError):
            watch_count = 0

        batch.append({"repo_name": repo_name, "watch_count": watch_count})
        count += 1

        if len(batch) >= BATCH_SIZE:
            session.run(query, rows=batch)
            batch = []
            print(f"  ...{count:,} repos loaded")

    if batch:
        session.run(query, rows=batch)

    print(f"Loaded {count:,} repositories.")
    return count


def load_licenses(session, filepath):
    """
    Loads Licenses.json, creating a License node per distinct license
    and linking each repository to the one it uses.

    Modeling the license as its own node rather than as a property on
    Repo is deliberate. As a property, finding every repository sharing
    a license means scanning repositories. As a node, it is one hop off
    a single License node, and licenses become something the graph can
    be traversed through rather than only filtered by.
    """
    query = """
    UNWIND $rows AS row
    MERGE (l:License {name: row.license})
    MERGE (r:Repo {name: row.repo_name})
    MERGE (r)-[:LICENSED_UNDER]->(l)
    """

    batch = []
    count = 0

    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        license_name = record.get("license")
        if not repo_name or not license_name:
            continue

        batch.append({"repo_name": repo_name, "license": license_name})
        count += 1

        if len(batch) >= BATCH_SIZE:
            session.run(query, rows=batch)
            batch = []
            print(f"  ...{count:,} license links created")

    if batch:
        session.run(query, rows=batch)

    print(f"Loaded license data for {count:,} repositories.")
    return count


def build_contribution_edges(session):
    """
    Derives the (Author)-[:CONTRIBUTED_TO {commits}]->(Repo)
    relationships by counting each author's commits per repository.

    This is the roll-up described in the module docstring. The pattern
    Author -> Commit -> Repo is matched once, grouped by the author and
    repo pair, and collapsed into one weighted edge. Every feature in
    this part traverses these edges rather than walking through commits,
    which is what keeps the collaboration and similarity queries fast.
    """
    print("Building contribution relationships...")
    result = session.run("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:IN_REPO]->(r:Repo)
        WITH a, r, count(c) AS commit_count
        MERGE (a)-[rel:CONTRIBUTED_TO]->(r)
          SET rel.commits = commit_count
        RETURN count(*) AS edges
    """)
    edges = result.single()["edges"]
    print(f"Created {edges:,} contribution relationships.")
    return edges


def load_all_data(data_dir="data"):
    """
    Main entry point called from main.py. Clears the graph, loads all
    three source files, then derives the contribution edges.

    Order matters. Commits are loaded first so the Repo nodes exist,
    the repo and license files then enrich those same nodes, and the
    contribution roll-up runs last because it reads the relationships
    the commit load created.
    """
    with get_session() as session:
        clear_graph(session)

        print("Loading commits...")
        load_commits(session, os.path.join(data_dir, "Sample_Commits.json"))

        print("Loading repos...")
        load_repos(session, os.path.join(data_dir, "Sample_Repos.json"))

        print("Loading licenses...")
        load_licenses(session, os.path.join(data_dir, "Licenses.json"))

        build_contribution_edges(session)

    print("All data loaded into Neo4j.")


if __name__ == "__main__":
    load_all_data("data")
