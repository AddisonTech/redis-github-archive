"""
sqlite_data_loader.py

Loads the GitHub Archive dataset into the normalized SQLite schema.
This is the SQLite counterpart to the loaders in parts 1 through 4.

The ordering problem
--------------------
A normalized schema cannot be loaded in any order. A commit row carries
a repo_id and an author_id, and with foreign keys enforced those rows
have to exist before the commit that references them. None of the four
NoSQL databases had this constraint, because none of them had real
referential integrity to violate. Here the load runs parents first:
licenses, then repos and authors, then commits, then the files each
commit touched.

Insert performance
------------------
Three things keep this fast, and all three are worth understanding
because the naive version of this loader is genuinely unusable on a file
this size.

First, executemany with a single transaction around each batch. SQLite
commits to disk at the end of every transaction by default, so inserting
rows one at a time with autocommit means one disk sync per row. Batching
into transactions turns hundreds of thousands of syncs into a few
hundred.

Second, journal and synchronous PRAGMAs relaxed during the bulk load.
These trade crash durability for speed, which is the right trade for a
load that can simply be re-run from the source files if it fails
partway. They are restored afterward.

Third, the id lookups are cached in Python dictionaries rather than
issued as a SELECT before every insert. Resolving a repo name to its
repo_id by querying the database once per commit would mean an extra
round trip for every single row.
"""

import json
import os
import sqlite3
from sqlite_config import get_connection, initialize_schema, DB_PATH

# Rows per executemany call. Large enough to amortize the transaction
# overhead, small enough that a batch stays comfortably in memory.
BATCH_SIZE = 5000


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


def reset_database(connection):
    """
    Drops every table and rebuilds the schema so a reload starts clean.

    Tables are dropped children first. With foreign keys enforced,
    dropping repos while commits still reference it would fail.
    """
    print("Clearing existing tables...")
    cursor = connection.cursor()
    for table in ["commit_files", "commits", "repos", "authors", "licenses"]:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    connection.commit()
    initialize_schema(connection)


def _apply_bulk_pragmas(connection):
    """
    Relaxes durability settings for the duration of the load. WAL keeps
    reads and writes from blocking each other, and synchronous OFF stops
    SQLite from waiting on the operating system to confirm each write
    reached the disk.
    """
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = OFF;")
    connection.execute("PRAGMA cache_size = -64000;")  # roughly 64 MB


def _restore_pragmas(connection):
    """
    Puts the durability settings back after loading finishes, so normal
    application use is not running with crash safety disabled.
    """
    connection.execute("PRAGMA synchronous = FULL;")


def load_licenses(connection, filepath):
    """
    Loads Licenses.json into the licenses and repos tables.

    Each distinct license becomes one row, and each repository is
    created with a foreign key pointing at it. INSERT OR IGNORE handles
    the repeats: the same license name appears on thousands of
    repositories, and only the first one needs to create the row.

    Returns a dictionary mapping repo_name to repo_id so the commit
    loader can resolve names without querying.
    """
    cursor = connection.cursor()
    license_rows = []
    repo_rows = []
    count = 0

    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        license_name = record.get("license")
        if not repo_name or not license_name:
            continue

        license_rows.append((license_name,))
        repo_rows.append((repo_name, license_name))
        count += 1

        if len(repo_rows) >= BATCH_SIZE:
            _flush_licenses(cursor, license_rows, repo_rows)
            connection.commit()
            license_rows, repo_rows = [], []
            print(f"  ...{count:,} license records processed")

    if repo_rows:
        _flush_licenses(cursor, license_rows, repo_rows)
        connection.commit()

    print(f"Loaded license data for {count:,} repositories.")
    return count


def _flush_licenses(cursor, license_rows, repo_rows):
    """
    Writes one batch of licenses and the repositories that use them.

    The repo insert resolves the license name to its id with a subquery
    rather than a second Python round trip. This is the kind of thing
    the NoSQL parts could not do at all: the value being inserted is
    looked up from another table inside the same statement.
    """
    cursor.executemany(
        "INSERT OR IGNORE INTO licenses (name) VALUES (?)", license_rows)
    cursor.executemany("""
        INSERT INTO repos (repo_name, license_id)
        VALUES (?, (SELECT license_id FROM licenses WHERE name = ?))
        ON CONFLICT(repo_name) DO UPDATE
          SET license_id = excluded.license_id
    """, repo_rows)


def load_repos(connection, filepath):
    """
    Loads Sample_Repos.json, setting watch counts on repository rows.

    Repositories already created by the license load are updated in
    place rather than duplicated, using ON CONFLICT. Repositories that
    appear only in this file are inserted fresh.

    watch_count arrives as a string in the source data and is converted
    here, because the features sort and bucket on it numerically.
    """
    cursor = connection.cursor()
    rows = []
    count = 0

    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        if not repo_name:
            continue
        try:
            watch_count = int(record.get("watch_count", 0))
        except (TypeError, ValueError):
            watch_count = 0

        rows.append((repo_name, watch_count))
        count += 1

        if len(rows) >= BATCH_SIZE:
            cursor.executemany("""
                INSERT INTO repos (repo_name, watch_count) VALUES (?, ?)
                ON CONFLICT(repo_name) DO UPDATE
                  SET watch_count = excluded.watch_count
            """, rows)
            connection.commit()
            rows = []
            print(f"  ...{count:,} repos loaded")

    if rows:
        cursor.executemany("""
            INSERT INTO repos (repo_name, watch_count) VALUES (?, ?)
            ON CONFLICT(repo_name) DO UPDATE
              SET watch_count = excluded.watch_count
        """, rows)
        connection.commit()

    print(f"Loaded {count:,} repositories.")
    return count


def load_commits(connection, filepath):
    """
    Loads Sample_Commits.json into the authors, repos, commits, and
    commit_files tables.

    The file is read in two passes. The first collects every distinct
    author and repository name so those parent rows exist before any
    commit references them. The second inserts the commits themselves
    along with the files they touched.

    Two passes over a large file is slower than one, but the alternative
    is resolving each parent row inside the commit loop, which costs a
    query per record. Reading the file twice is cheaper than that, and
    it is the price of having the database enforce referential integrity
    rather than trusting the application to.
    """
    cursor = connection.cursor()

    # Pass one: parent rows.
    print("  pass 1 of 2: collecting authors and repositories...")
    authors = {}
    repo_names = set()
    for record in _stream_json_lines(filepath):
        repo_name = record.get("repo_name")
        if not record.get("commit") or not repo_name:
            continue
        author = record.get("author") or {}
        name = author.get("name", "unknown")
        # First email seen for an author wins; the dataset has the same
        # person committing under several addresses.
        authors.setdefault(name, author.get("email", ""))
        repo_names.add(repo_name)

    cursor.executemany(
        "INSERT OR IGNORE INTO authors (name, email) VALUES (?, ?)",
        list(authors.items()))
    cursor.executemany(
        "INSERT OR IGNORE INTO repos (repo_name) VALUES (?)",
        [(name,) for name in repo_names])
    connection.commit()
    print(f"    {len(authors):,} authors, {len(repo_names):,} repositories")

    # Cache the generated ids so the commit loop never queries for them.
    author_ids = {row["name"]: row["author_id"] for row in
                  cursor.execute("SELECT author_id, name FROM authors")}
    repo_ids = {row["repo_name"]: row["repo_id"] for row in
                cursor.execute("SELECT repo_id, repo_name FROM repos")}

    # Pass two: the commits and their files.
    print("  pass 2 of 2: loading commits and file changes...")
    commit_rows = []
    file_rows = []
    count = 0

    for record in _stream_json_lines(filepath):
        commit_hash = record.get("commit")
        repo_name = record.get("repo_name")
        if not commit_hash or not repo_name:
            continue

        author = record.get("author") or {}
        author_name = author.get("name", "unknown")
        difference = record.get("difference") or []

        repo_id = repo_ids.get(repo_name)
        author_id = author_ids.get(author_name)
        if repo_id is None or author_id is None:
            continue

        commit_rows.append((
            commit_hash, repo_id, author_id,
            record.get("subject", ""), record.get("message", ""),
            len(difference),
        ))
        for change in difference:
            path = change.get("new_path")
            if path:
                file_rows.append((commit_hash, path))

        count += 1
        if len(commit_rows) >= BATCH_SIZE:
            _flush_commits(cursor, commit_rows, file_rows)
            connection.commit()
            commit_rows, file_rows = [], []
            print(f"  ...{count:,} commits loaded")

    if commit_rows:
        _flush_commits(cursor, commit_rows, file_rows)
        connection.commit()

    print(f"Loaded {count:,} commits.")
    return count


def _flush_commits(cursor, commit_rows, file_rows):
    """
    Writes one batch of commits and their file changes. Commits go in
    first, since commit_files carries a foreign key to them.
    """
    cursor.executemany("""
        INSERT OR IGNORE INTO commits
            (commit_hash, repo_id, author_id, subject, message,
             num_files_changed)
        VALUES (?, ?, ?, ?, ?, ?)
    """, commit_rows)
    if file_rows:
        cursor.executemany(
            "INSERT INTO commit_files (commit_hash, file_path) VALUES (?, ?)",
            file_rows)


def print_summary(connection):
    """
    Prints a row count per table after loading, so the user can confirm
    the load did what it was supposed to.
    """
    print("\nRow counts:")
    for table in ["licenses", "authors", "repos", "commits", "commit_files"]:
        row = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        print(f"  {table:<14} {row['n']:>12,}")


def load_all_data(data_dir="data"):
    """
    Main entry point called from main.py. Rebuilds the schema, loads all
    three source files in dependency order, then runs ANALYZE.

    ANALYZE collects statistics about the contents of each table and
    index. SQLite's query planner uses those statistics to choose join
    order, and without them it guesses. Running it once after loading is
    the cheapest performance improvement available to the features.
    """
    connection = get_connection()
    try:
        reset_database(connection)
        _apply_bulk_pragmas(connection)

        print("Loading licenses...")
        load_licenses(connection, os.path.join(data_dir, "Licenses.json"))

        print("Loading repos...")
        load_repos(connection, os.path.join(data_dir, "Sample_Repos.json"))

        print("Loading commits...")
        load_commits(connection, os.path.join(data_dir, "Sample_Commits.json"))

        print("Collecting query planner statistics...")
        connection.execute("ANALYZE;")
        connection.commit()

        _restore_pragmas(connection)
        print_summary(connection)
        print(f"\nAll data loaded into {DB_PATH}")
    except FileNotFoundError as error:
        print(f"\nCould not find a dataset file: {error.filename}")
        print("Place Sample_Commits.json, Sample_Repos.json, and "
              "Licenses.json in the data/ folder and try again.")
    except sqlite3.Error as error:
        print(f"\nSQLite error during load: {error}")
    finally:
        connection.close()


if __name__ == "__main__":
    load_all_data("data")
