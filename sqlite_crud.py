"""
sqlite_crud.py

CRUD operations on commit rows stored in SQLite. This is the SQLite
counterpart to the CRUD modules in parts 1 through 4.

Two things here are different from every earlier part.

Deletes clean up after themselves. commit_files declares its foreign key
with ON DELETE CASCADE, so removing a commit removes its file rows
inside the database. Redis and Cassandra both required the application
to walk every derived structure by hand and would happily leave orphans
if it forgot. Neo4j refused the delete outright until the relationships
were removed. SQLite is the only one of the five that quietly does the
right thing, and it only does so because the PRAGMA in sqlite_config.py
turned enforcement on.

Multi-step writes are atomic. Creating a commit touches three tables,
since the author and repository rows have to exist first. Wrapping that
in a transaction means either all of it lands or none of it does. The
closest any earlier part came was Cassandra's logged batch, which
guarantees eventual application but gives no isolation, and its
lightweight transaction, which covers a single partition. A real
rollback across several tables is something none of the four NoSQL
databases offered.

Every query is parameterized with ? placeholders. String formatting a
user-entered commit hash into SQL would be a textbook injection hole,
and unlike the Cypher and CQL parts, SQL is a language where the
consequences are severe and well understood.
"""

import sqlite3
from sqlite_config import get_connection

# Columns on the commits table the update path is allowed to change.
# The hash is excluded because it is the primary key, and repo_id and
# author_id are excluded because changing a relationship is a different
# operation from editing a field.
UPDATABLE_FIELDS = {"subject", "message", "num_files_changed"}


def create_record(connection, commit_hash, repo_name, author_name, subject,
                  message=""):
    """
    Creates a commit, creating its author and repository rows first if
    they do not already exist. Returns False if the hash is taken.

    The whole thing runs in one transaction. If the commit insert fails
    after the author and repo inserts succeeded, the rollback removes
    those too rather than leaving a repository behind that has no
    commits and was never meant to exist.
    """
    cursor = connection.cursor()

    existing = cursor.execute(
        "SELECT 1 FROM commits WHERE commit_hash = ?", (commit_hash,)
    ).fetchone()
    if existing:
        return False

    try:
        cursor.execute("BEGIN")

        cursor.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)",
                       (author_name,))
        cursor.execute("INSERT OR IGNORE INTO repos (repo_name) VALUES (?)",
                       (repo_name,))

        cursor.execute("""
            INSERT INTO commits
                (commit_hash, repo_id, author_id, subject, message,
                 num_files_changed)
            VALUES (
                ?,
                (SELECT repo_id FROM repos WHERE repo_name = ?),
                (SELECT author_id FROM authors WHERE name = ?),
                ?, ?, 0)
        """, (commit_hash, repo_name, author_name, subject, message))

        connection.commit()
        return True
    except sqlite3.Error as error:
        connection.rollback()
        print(f"  Insert failed and was rolled back: {error}")
        return False


def read_record(connection, commit_hash):
    """
    Returns one commit joined to its author and repository, or None.

    The join is the point. In the document and column-family parts this
    information was either duplicated into the record at load time or
    required separate lookups. Here it is stored once and assembled on
    demand, which is the trade a relational database makes: slightly
    more work at read time in exchange for never having two copies of a
    fact that can disagree.
    """
    row = connection.execute("""
        SELECT c.commit_hash,
               c.subject,
               c.message,
               c.num_files_changed,
               a.name  AS author_name,
               a.email AS author_email,
               r.repo_name,
               r.watch_count,
               l.name  AS license_name
        FROM commits c
        JOIN authors a  ON a.author_id = c.author_id
        JOIN repos   r  ON r.repo_id   = c.repo_id
        LEFT JOIN licenses l ON l.license_id = r.license_id
        WHERE c.commit_hash = ?
    """, (commit_hash,)).fetchone()

    return dict(row) if row else None


def read_files_for(connection, commit_hash, limit=10):
    """
    Returns the file paths a commit touched. Kept separate from
    read_record because joining it in would repeat every commit column
    once per file.
    """
    rows = connection.execute("""
        SELECT file_path FROM commit_files
        WHERE commit_hash = ?
        ORDER BY file_path
        LIMIT ?
    """, (commit_hash, limit)).fetchall()
    return [row["file_path"] for row in rows]


def update_record(connection, commit_hash, field, value):
    """
    Updates a single column on an existing commit. Returns False if the
    commit does not exist and None if the column is not updatable.

    Column names cannot be parameterized in SQL, the same restriction
    CQL and Cypher have, so the field is validated against a fixed
    allowlist before being formatted into the statement. The value
    itself is always bound.
    """
    if field not in UPDATABLE_FIELDS:
        return None

    if field == "num_files_changed":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None

    cursor = connection.cursor()
    cursor.execute(f"UPDATE commits SET {field} = ? WHERE commit_hash = ?",
                   (value, commit_hash))
    connection.commit()

    # rowcount reports how many rows the statement actually changed,
    # which is a direct answer to whether the commit existed. None of
    # the four NoSQL parts could tell the difference without a separate
    # read first.
    return cursor.rowcount > 0


def delete_record(connection, commit_hash):
    """
    Deletes a commit. Its rows in commit_files go with it automatically
    through ON DELETE CASCADE.

    The file count is read first only so the menu can report what the
    cascade removed. The delete itself needs no help.
    """
    cursor = connection.cursor()

    file_count = cursor.execute(
        "SELECT COUNT(*) AS n FROM commit_files WHERE commit_hash = ?",
        (commit_hash,)).fetchone()["n"]

    cursor.execute("DELETE FROM commits WHERE commit_hash = ?", (commit_hash,))
    connection.commit()

    if cursor.rowcount == 0:
        return None
    return file_count


def search_by_author(connection, author_name, limit=10):
    """
    Finds commits by author using a case-insensitive LIKE, returning the
    repository alongside each commit.

    Worth comparing across the five parts. Redis could not do this at
    all without a purpose-built index. MongoDB used a regex query.
    Cassandra needed a table designed for it in advance. Neo4j matched a
    pattern from the author node outward. SQL expresses it as a
    predicate on a joined column, and the query planner decides how to
    execute it.
    """
    rows = connection.execute("""
        SELECT c.commit_hash, a.name AS author_name,
               r.repo_name, c.subject
        FROM commits c
        JOIN authors a ON a.author_id = c.author_id
        JOIN repos   r ON r.repo_id   = c.repo_id
        WHERE a.name LIKE ? COLLATE NOCASE
        ORDER BY r.repo_name
        LIMIT ?
    """, (f"%{author_name}%", limit)).fetchall()
    return [dict(row) for row in rows]


def list_loaded_repos(connection, limit=25):
    """
    Returns repository names that have commit data, so the menus can
    show the user valid choices.
    """
    rows = connection.execute("""
        SELECT r.repo_name, COUNT(*) AS commit_count
        FROM commits c
        JOIN repos r ON r.repo_id = c.repo_id
        GROUP BY r.repo_name
        ORDER BY commit_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [(row["repo_name"], row["commit_count"]) for row in rows]


def run_crud_menu():
    """
    Text menu exercising all four CRUD operations plus author search.
    """
    connection = get_connection()
    try:
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
                elif create_record(connection, commit_hash, repo_name,
                                   author_name, subject):
                    print("Commit created and linked to its author and repo.")
                else:
                    print("A commit with that hash already exists.")

            elif choice == "2":
                commit_hash = input("Commit hash to look up: ").strip()
                record = read_record(connection, commit_hash)
                if record:
                    for field, value in record.items():
                        print(f"  {field}: {value}")
                    files = read_files_for(connection, commit_hash)
                    if files:
                        print(f"  files touched ({len(files)} shown):")
                        for path in files:
                            print(f"    {path}")
                else:
                    print("No commit found with that hash.")

            elif choice == "3":
                commit_hash = input("Commit hash to update: ").strip()
                field = input("Field to update (subject, message, "
                              "num_files_changed): ").strip()
                value = input("New value: ").strip()
                result = update_record(connection, commit_hash, field, value)
                if result is None:
                    print("That field cannot be updated. Try subject, "
                          "message, or num_files_changed.")
                elif result:
                    print("Commit updated.")
                else:
                    print("No commit found with that hash.")

            elif choice == "4":
                commit_hash = input("Commit hash to delete: ").strip()
                result = delete_record(connection, commit_hash)
                if result is None:
                    print("No commit found with that hash.")
                else:
                    print(f"Commit deleted. {result} file row(s) removed "
                          f"automatically by the foreign key cascade.")

            elif choice == "5":
                author_name = input("Author name to search for: ").strip()
                results = search_by_author(connection, author_name)
                if not results:
                    print("No commits found for that author.")
                else:
                    print(f"\nFound {len(results)} commit(s):")
                    for record in results:
                        print(f"  [{record['commit_hash'][:10]}] "
                              f"{record['repo_name']}: "
                              f"{(record['subject'] or '')[:50]}")

            elif choice == "6":
                break
            else:
                print("Not a valid option, try again.")
    finally:
        connection.close()


if __name__ == "__main__":
    run_crud_menu()
