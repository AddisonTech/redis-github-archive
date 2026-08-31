"""
sqlite_config.py

Shared SQLite connection setup and schema definition. This is the SQLite
counterpart to redis_config.py (part 1), mongo_config.py (part 2),
cassandra_config.py (part 3), and neo4j_config.py (part 4).

SQLite is the only relational database in this project and the only one
of the five that needs no server at all. There is no host, no port, and
no credentials, because the database is a single file on disk and the
library runs inside the application process. That alone is worth noting
after four parts spent starting services and setting passwords.

What the schema does that none of the earlier four could
-------------------------------------------------------
This is a normalized schema. Each fact is stored exactly once and
referenced by foreign key everywhere else it is needed. Every earlier
part had to denormalize in some form: Redis hand-built parallel index
structures, Cassandra wrote the same commit into two tables, Neo4j
derived a redundant relationship to keep traversals cheap, and MongoDB
embedded values that a relational schema would have pointed at. None of
that is necessary here, because the join is done at query time rather
than designed around in advance.

Foreign keys are declared with ON DELETE CASCADE, which means the
cleanup that Redis and Cassandra both required the application to
perform by hand happens inside the database. Deleting a commit removes
its file rows automatically. Note that SQLite ships with foreign key
enforcement OFF by default for backward compatibility, so the PRAGMA in
get_connection() is not optional decoration; without it the constraints
below are documentation rather than rules.
"""

import os
import sqlite3

# The database is a single file in the project root. Delete it and the
# database is gone, which is also how the loader resets.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "github_archive.db")

# Tables, in dependency order. Parents are created before the children
# that reference them.
SCHEMA_STATEMENTS = [

    # Licenses referenced by repos. Stored once and pointed at, rather
    # than repeated as a string on every repository row.
    """
    CREATE TABLE IF NOT EXISTS licenses (
        license_id INTEGER PRIMARY KEY,
        name       TEXT NOT NULL UNIQUE
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS authors (
        author_id INTEGER PRIMARY KEY,
        name      TEXT NOT NULL UNIQUE,
        email     TEXT
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS repos (
        repo_id     INTEGER PRIMARY KEY,
        repo_name   TEXT NOT NULL UNIQUE,
        watch_count INTEGER DEFAULT 0,
        license_id  INTEGER REFERENCES licenses(license_id)
                    ON DELETE SET NULL
    );
    """,

    # The commit hash is the natural primary key, so it is used directly
    # rather than adding a surrogate integer id alongside it.
    """
    CREATE TABLE IF NOT EXISTS commits (
        commit_hash       TEXT PRIMARY KEY,
        repo_id           INTEGER NOT NULL REFERENCES repos(repo_id)
                          ON DELETE CASCADE,
        author_id         INTEGER NOT NULL REFERENCES authors(author_id)
                          ON DELETE CASCADE,
        subject           TEXT,
        message           TEXT,
        num_files_changed INTEGER DEFAULT 0
    );
    """,

    # One row per file touched by a commit. ON DELETE CASCADE is what
    # makes deleting a commit clean up after itself.
    """
    CREATE TABLE IF NOT EXISTS commit_files (
        file_id     INTEGER PRIMARY KEY,
        commit_hash TEXT NOT NULL REFERENCES commits(commit_hash)
                    ON DELETE CASCADE,
        file_path   TEXT NOT NULL
    );
    """,
]

# Indexes on the foreign key columns and on anything the features sort
# by. SQLite indexes a PRIMARY KEY and a UNIQUE column automatically but
# not a REFERENCES column, and every feature in this section joins on
# those, so without these the query planner falls back to scanning.
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo_id);",
    "CREATE INDEX IF NOT EXISTS idx_commits_author ON commits(author_id);",
    "CREATE INDEX IF NOT EXISTS idx_files_commit ON commit_files(commit_hash);",
    "CREATE INDEX IF NOT EXISTS idx_repos_watch ON repos(watch_count DESC);",
    "CREATE INDEX IF NOT EXISTS idx_repos_license ON repos(license_id);",
]


def get_connection():
    """
    Returns a connection to the database file with the settings the rest
    of the application expects.

    Two settings matter here. row_factory returns rows that can be
    addressed by column name instead of by position, which keeps the
    feature modules readable. The foreign_keys PRAGMA turns on
    constraint enforcement, and it has to be set per connection rather
    than once on the database, because SQLite treats it as a connection
    level setting.
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_schema(connection):
    """
    Creates every table and index if they do not already exist. Safe to
    call repeatedly, which is why the loader and the menus can both call
    it without coordinating.
    """
    cursor = connection.cursor()
    for statement in SCHEMA_STATEMENTS + INDEX_STATEMENTS:
        cursor.execute(statement)
    connection.commit()


def database_exists():
    """
    Returns True if the database file is present on disk. Used by the
    menu to tell the difference between an empty database and one that
    was never created.
    """
    return os.path.exists(DB_PATH)


def has_data(connection):
    """
    Returns True if commits have been loaded, so a feature can give a
    useful message instead of printing an empty report.
    """
    try:
        row = connection.execute("SELECT COUNT(*) AS n FROM commits").fetchone()
        return row["n"] > 0
    except sqlite3.Error:
        return False


def check_connection():
    """
    Confirms the database file can be opened and the schema applied.
    Returns True on success and False on failure, matching the interface
    the other four config modules expose so main.py treats every section
    the same way.

    Unlike the earlier four parts this practically cannot fail for
    connection reasons, since there is no server to be down. A failure
    here means a file permission problem or a corrupt database file.
    """
    try:
        connection = get_connection()
        initialize_schema(connection)
        connection.close()
        return True
    except sqlite3.Error as error:
        print(f"  SQLite error: {error}")
        return False


if __name__ == "__main__":
    # Run this file directly to create the database file and confirm the
    # schema applies cleanly before loading any data.
    if check_connection():
        conn = get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "ORDER BY name").fetchall()
        print(f"Database ready at {DB_PATH}")
        print("Tables:", ", ".join(row["name"] for row in tables))
        conn.close()
    else:
        print("Could not open or initialize the SQLite database.")
