"""
feature_sqlite_file_activity.py

SQLite feature 1: file change activity in the most popular repositories,
ranked by watch count.

This is the multi-table join the whole normalized schema exists to
support. The query reaches across four tables in one statement:
commit_files for the changes, commits to reach the repository,
repos for the watch count, and licenses for the license name. Nothing
was duplicated at load time to make it possible, and no structure was
built in advance to serve this particular question.

That is the contrast with every earlier part. Redis and Cassandra both
had to decide during loading which questions they would be able to
answer. MongoDB could aggregate freely but only within one collection at
a time, since it has no real join. Neo4j could traverse across
everything but expresses the work as a path rather than a set. SQL
states the relationship between four tables and lets the query planner
decide how to satisfy it, which is why ANALYZE runs at the end of the
load.

Uses Sample_Commits.json for the file changes, Sample_Repos.json for the
watch counts, and Licenses.json for the license names.
"""

from sqlite_config import get_connection, has_data


def get_file_activity(top_n=15):
    """
    Returns the most watched repositories that have commit data, along
    with their commit count, how many distinct files were touched, the
    total number of file changes, and the average files per commit.

    COUNT(DISTINCT f.file_path) and COUNT(f.file_id) answer two
    different questions from the same join. The first is how much of
    the codebase was touched, the second is how much churn there was.
    A repository where one file changes two hundred times and one where
    two hundred files change once each look identical on the second
    number and nothing alike on the first.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT r.repo_name,
                   r.watch_count,
                   COALESCE(l.name, 'none') AS license_name,
                   COUNT(DISTINCT c.commit_hash) AS commit_count,
                   COUNT(DISTINCT f.file_path)   AS distinct_files,
                   COUNT(f.file_id)              AS total_changes,
                   ROUND(
                       CAST(COUNT(f.file_id) AS REAL) /
                       COUNT(DISTINCT c.commit_hash), 1
                   ) AS avg_files_per_commit
            FROM repos r
            JOIN commits c        ON c.repo_id = r.repo_id
            LEFT JOIN commit_files f ON f.commit_hash = c.commit_hash
            LEFT JOIN licenses l  ON l.license_id = r.license_id
            GROUP BY r.repo_id
            ORDER BY r.watch_count DESC
            LIMIT ?
        """, (top_n,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_busiest_files(top_n=10):
    """
    Returns the individual files changed most often across the dataset,
    with the repository each belongs to.

    HAVING is what makes this useful rather than noisy. It filters on
    the result of the aggregate, which WHERE cannot do because WHERE is
    evaluated before rows are grouped. Requiring at least two changes
    drops the long tail of files touched exactly once, which would
    otherwise be most of the table.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT f.file_path,
                   r.repo_name,
                   COUNT(*) AS change_count,
                   COUNT(DISTINCT c.author_id) AS distinct_authors
            FROM commit_files f
            JOIN commits c ON c.commit_hash = f.commit_hash
            JOIN repos   r ON r.repo_id     = c.repo_id
            GROUP BY f.file_path, r.repo_id
            HAVING COUNT(*) > 1
            ORDER BY change_count DESC
            LIMIT ?
        """, (top_n,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def print_file_activity_report(top_n=15):
    """
    Prints file activity for the most watched repositories, then the
    individual files that changed most often. This is what main.py calls
    for this feature.
    """
    connection = get_connection()
    loaded = has_data(connection)
    connection.close()

    if not loaded:
        print("\nNo data found. Choose the load option first.")
        return

    results = get_file_activity(top_n)

    print("\nFile Activity in the Most Watched Repositories (SQLite):")
    print(f"  {'Repository':<28} {'Watchers':>9} {'Commits':>8} "
          f"{'Files':>8} {'Changes':>9} {'Avg/Commit':>11}")
    print("  " + "-" * 78)
    for record in results:
        print(f"  {record['repo_name'][:28]:<28} "
              f"{record['watch_count']:>9,} "
              f"{record['commit_count']:>8,} "
              f"{record['distinct_files']:>8,} "
              f"{record['total_changes']:>9,} "
              f"{record['avg_files_per_commit'] or 0:>11}")

    print("\nMost Frequently Changed Files:")
    busiest = get_busiest_files(10)
    if not busiest:
        print("  No file changed more than once in the loaded data.")
        return

    for rank, record in enumerate(busiest, start=1):
        print(f"  {rank:>2}. {record['file_path'][:34]:<34} "
              f"{record['repo_name'][:22]:<22} "
              f"{record['change_count']:>4} changes by "
              f"{record['distinct_authors']} author(s)")


if __name__ == "__main__":
    print_file_activity_report()
