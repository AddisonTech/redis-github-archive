"""
cassandra_data_loader.py

Loads the GitHub Archive dataset into Cassandra. This is the Cassandra
counterpart to data_loader.py (Redis) and mongo_data_loader.py
(MongoDB).

Three things about this loader are specific to Cassandra and worth
pointing out, since they are the parts that would look wrong to someone
coming from a relational or document database:

1. Every commit is written to two tables. commits_by_hash serves CRUD
   lookups and commits_by_repo serves per-repository browsing. Cassandra
   has no secondary index worth relying on at scale, so the same data is
   stored once per access pattern.

2. Aggregates are maintained at write time using counter columns rather
   than computed at read time. There is no server-side GROUP BY to fall
   back on, so if the application needs a count it has to be counted on
   the way in.

3. Writes go out through prepared statements executed concurrently.
   A prepared statement is parsed once and reused, and the driver's
   concurrent helper keeps a fixed number of requests in flight instead
   of blocking on each one, which is the difference between minutes and
   hours on a file this size.

Tables are truncated before loading so the load step is repeatable.
Counter tables in particular have to be truncated rather than
overwritten, because a counter update adds to whatever is already there.
"""

import json
import os
from cassandra.concurrent import execute_concurrent_with_args
from cassandra_config import get_session, GLOBAL_BUCKET

# How many requests the driver keeps in flight at once. Higher values
# load faster but a single node will start shedding load if pushed too
# far, so 64 is a reasonable middle ground for a lab machine.
CONCURRENCY = 64

# How many rows to gather before handing a chunk to the driver. This
# keeps memory flat while streaming a file that does not fit in RAM.
CHUNK_SIZE = 5000

# Watch count tier boundaries, used as partition keys in
# repos_by_watch_tier. The ranges widen as they go up because watch
# counts are heavily skewed, with most repos near zero and a handful in
# the tens of thousands.
WATCH_TIERS = [
    (0, 0, "0 watchers"),
    (1, 9, "1 to 9"),
    (10, 99, "10 to 99"),
    (100, 999, "100 to 999"),
    (1000, 9999, "1,000 to 9,999"),
    (10000, None, "10,000+"),
]

TIER_ORDER = [tier[2] for tier in WATCH_TIERS]

TABLES = [
    "commits_by_hash",
    "commits_by_repo",
    "commit_counts_by_author",
    "repos_by_watch_tier",
    "repo_counts_by_tier",
    "license_counts",
    "repos_loaded",
]


def watch_tier_for(watch_count):
    """
    Maps a raw watch count onto the tier label used as the partition
    key in repos_by_watch_tier.
    """
    for low, high, label in WATCH_TIERS:
        if watch_count >= low and (high is None or watch_count <= high):
            return label
    return "0 watchers"


def truncate_all(session):
    """
    Empties every table so a reload starts from a known state. This
    matters more here than in the other two implementations because
    counter columns accumulate, so loading twice without truncating
    would double every count.
    """
    print("Clearing existing tables...")
    for table in TABLES:
        session.execute(f"TRUNCATE {table};")


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


def _run_chunk(session, statement, rows):
    """
    Executes one prepared statement against many rows concurrently and
    reports anything that failed rather than silently dropping it.
    """
    if not rows:
        return
    results = execute_concurrent_with_args(
        session, statement, rows, concurrency=CONCURRENCY, raise_on_first_error=False)
    for success, outcome in results:
        if not success:
            print(f"  write failed: {outcome}")


def load_commits(session, filepath):
    """
    Loads Sample_Commits.json into the two commit tables and builds the
    per-author commit counters as it goes.
    """
    insert_by_hash = session.prepare("""
        INSERT INTO commits_by_hash (
            commit_hash, repo_name, author_name, author_email,
            committer_name, subject, message, tree,
            files_changed, num_files_changed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)

    insert_by_repo = session.prepare("""
        INSERT INTO commits_by_repo (
            repo_name, commit_hash, author_name, subject, num_files_changed)
        VALUES (?, ?, ?, ?, ?)
    """)

    # Counters are updated, never inserted. Cassandra rejects INSERT on
    # a table containing a counter column.
    bump_author = session.prepare("""
        UPDATE commit_counts_by_author
        SET commit_count = commit_count + 1
        WHERE repo_name = ? AND author_name = ?
    """)

    insert_repo_name = session.prepare("""
        INSERT INTO repos_loaded (bucket, repo_name) VALUES (?, ?)
    """)

    hash_rows, repo_rows, author_rows = [], [], []
    repos_seen = set()
    count = 0

    for record in _stream_json_lines(filepath):
        commit_hash = record.get("commit")
        repo_name = record.get("repo_name")
        if not commit_hash or not repo_name:
            continue

        author = record.get("author") or {}
        committer = record.get("committer") or {}
        difference = record.get("difference") or []
        author_name = author.get("name", "unknown")
        subject = record.get("subject", "")
        files_changed = [d.get("new_path") for d in difference
                         if d.get("new_path")]

        hash_rows.append((
            commit_hash, repo_name, author_name, author.get("email", ""),
            committer.get("name", "unknown"), subject,
            record.get("message", ""), record.get("tree", ""),
            files_changed, len(difference),
        ))
        repo_rows.append((
            repo_name, commit_hash, author_name, subject, len(difference)))
        author_rows.append((repo_name, author_name))
        repos_seen.add(repo_name)

        count += 1
        if len(hash_rows) >= CHUNK_SIZE:
            _run_chunk(session, insert_by_hash, hash_rows)
            _run_chunk(session, insert_by_repo, repo_rows)
            _run_chunk(session, bump_author, author_rows)
            hash_rows, repo_rows, author_rows = [], [], []
            print(f"  ...{count:,} commits loaded")

    _run_chunk(session, insert_by_hash, hash_rows)
    _run_chunk(session, insert_by_repo, repo_rows)
    _run_chunk(session, bump_author, author_rows)

    for repo_name in repos_seen:
        session.execute(insert_repo_name, (GLOBAL_BUCKET, repo_name))

    print(f"Loaded {count:,} commits across {len(repos_seen)} repositories.")
    return count


def load_repos(session, filepath):
    """
    Loads Sample_Repos.json into repos_by_watch_tier and maintains the
    per-tier counters used by the distribution histogram.

    watch_count arrives as a string in the source data and is converted
    to an integer here, because it is a clustering column typed as int
    and the descending sort on it has to be numeric to mean anything.
    """
    insert_repo = session.prepare("""
        INSERT INTO repos_by_watch_tier (watch_tier, watch_count, repo_name)
        VALUES (?, ?, ?)
    """)

    bump_tier = session.prepare("""
        UPDATE repo_counts_by_tier
        SET repo_count = repo_count + 1
        WHERE bucket = ? AND watch_tier = ?
    """)

    repo_rows, tier_rows = [], []
    count = 0

    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        if not repo_name:
            continue
        try:
            watch_count = int(record.get("watch_count", 0))
        except (TypeError, ValueError):
            watch_count = 0

        tier = watch_tier_for(watch_count)
        repo_rows.append((tier, watch_count, repo_name))
        tier_rows.append((GLOBAL_BUCKET, tier))

        count += 1
        if len(repo_rows) >= CHUNK_SIZE:
            _run_chunk(session, insert_repo, repo_rows)
            _run_chunk(session, bump_tier, tier_rows)
            repo_rows, tier_rows = [], []
            print(f"  ...{count:,} repos loaded")

    _run_chunk(session, insert_repo, repo_rows)
    _run_chunk(session, bump_tier, tier_rows)

    print(f"Loaded {count:,} repositories.")
    return count


def load_licenses(session, filepath):
    """
    Loads Licenses.json by incrementing one counter per license. The
    raw rows are not stored, because the only question asked of this
    file is how many repositories use each license.
    """
    bump_license = session.prepare("""
        UPDATE license_counts
        SET repo_count = repo_count + 1
        WHERE bucket = ? AND license_name = ?
    """)

    rows = []
    count = 0

    for record in _stream_json_lines(filepath):
        license_name = record.get("license")
        if not license_name:
            continue
        rows.append((GLOBAL_BUCKET, license_name))
        count += 1

        if len(rows) >= CHUNK_SIZE:
            _run_chunk(session, bump_license, rows)
            rows = []
            print(f"  ...{count:,} license records counted")

    _run_chunk(session, bump_license, rows)
    print(f"Loaded license data for {count:,} repositories.")
    return count


def load_all_data(data_dir="data"):
    """
    Main entry point called from main.py. Truncates every table, then
    loads all three source files.
    """
    session = get_session()

    truncate_all(session)

    print("Loading commits...")
    load_commits(session, os.path.join(data_dir, "Sample_Commits.json"))

    print("Loading repos...")
    load_repos(session, os.path.join(data_dir, "Sample_Repos.json"))

    print("Loading licenses...")
    load_licenses(session, os.path.join(data_dir, "Licenses.json"))

    print("All data loaded into Cassandra.")


if __name__ == "__main__":
    load_all_data("data")
