"""
feature_sqlite_contributor_ranking.py

SQLite feature 3: the top contributors within every repository, ranked
side by side, using window functions.

Why this feature is here
------------------------
Getting the top three contributors for one repository is easy in any
database in this project. Getting the top three for every repository in
a single query is not, and that is the distinction this feature exists
to demonstrate.

An ordinary GROUP BY collapses each group into one row, so it can return
each repository's single best contributor but cannot return its top
three without running one query per repository. A window function does
not collapse anything. It computes a value across a set of rows related
to the current row while leaving every row intact, so the ranking is
computed per repository and the individual rows survive to be filtered.

    ROW_NUMBER() OVER (PARTITION BY repo_id ORDER BY commits DESC)

PARTITION BY restarts the numbering for each repository, ORDER BY
decides what the numbering means, and the outer query keeps the rows
where the number is small enough. The result is one pass over the data
instead of one query per repository.

Nothing else in this project can do this. Cassandra has no aggregation
at all. Redis had to precompute ranks into sorted sets at write time.
MongoDB can approximate it with $group and $push followed by $slice, but
that materializes every group's full member list in memory first. Neo4j
can collect and slice per node but has no ranking construct. SQL
window functions, available in SQLite since version 3.25, express it
directly.

The second report uses SUM() OVER (), a window function with an empty
frame, to put each repository's share of the total alongside its own
row without a second query or a self join.

Uses Sample_Commits.json and Sample_Repos.json.
"""

import sqlite3
from sqlite_config import get_connection, has_data

# Window functions require SQLite 3.25 or later, released in 2018. Any
# Python 3.10 install will comfortably exceed that, but the check gives
# a clear message rather than a syntax error if it ever does not.
MIN_SQLITE_VERSION = (3, 25, 0)


def window_functions_supported():
    """
    Returns True if the bundled SQLite is new enough for window
    functions.
    """
    version = tuple(int(part) for part in sqlite3.sqlite_version.split("."))
    return version >= MIN_SQLITE_VERSION


def get_top_contributors_per_repo(per_repo=3, repo_limit=10):
    """
    Returns the top contributors within each repository, as a flat list
    of rows carrying the repository, the author, their commit count, and
    their rank inside that repository.

    Two window functions run here. ROW_NUMBER assigns the rank inside
    each repository, and SUM(...) OVER (PARTITION BY repo_id) puts the
    repository's total commit count on every one of its rows, which is
    what makes the percentage share possible without a second pass.

    The ranking is computed in a CTE and filtered in the outer query,
    because a window function cannot appear in a WHERE clause. WHERE is
    evaluated before the window functions run, so the rank does not
    exist yet at that point.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            WITH author_totals AS (
                SELECT c.repo_id,
                       c.author_id,
                       COUNT(*) AS commits
                FROM commits c
                GROUP BY c.repo_id, c.author_id
            ),
            ranked AS (
                SELECT t.repo_id,
                       t.author_id,
                       t.commits,
                       ROW_NUMBER() OVER (
                           PARTITION BY t.repo_id
                           ORDER BY t.commits DESC, t.author_id
                       ) AS rank_in_repo,
                       SUM(t.commits) OVER (
                           PARTITION BY t.repo_id
                       ) AS repo_total
                FROM author_totals t
            )
            SELECT r.repo_name,
                   a.name AS author_name,
                   ranked.commits,
                   ranked.rank_in_repo,
                   ranked.repo_total,
                   ROUND(100.0 * ranked.commits / ranked.repo_total, 1)
                       AS pct_of_repo
            FROM ranked
            JOIN repos   r ON r.repo_id   = ranked.repo_id
            JOIN authors a ON a.author_id = ranked.author_id
            WHERE ranked.rank_in_repo <= ?
              AND ranked.repo_id IN (
                    SELECT repo_id FROM commits
                    GROUP BY repo_id
                    ORDER BY COUNT(*) DESC
                    LIMIT ?
              )
            ORDER BY ranked.repo_total DESC, r.repo_name, ranked.rank_in_repo
        """, (per_repo, repo_limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_contribution_concentration(top_n=10):
    """
    Returns, for each repository, what share of its commits came from
    its single most active contributor.

    This is a concentration measure. A repository where one person wrote
    ninety percent of the commits is a different kind of project from
    one where the top contributor wrote five percent, and the number
    says which is which.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            WITH author_totals AS (
                SELECT repo_id, author_id, COUNT(*) AS commits
                FROM commits
                GROUP BY repo_id, author_id
            ),
            ranked AS (
                SELECT repo_id, author_id, commits,
                       ROW_NUMBER() OVER (
                           PARTITION BY repo_id ORDER BY commits DESC
                       ) AS rn,
                       SUM(commits) OVER (PARTITION BY repo_id) AS total,
                       COUNT(*) OVER (PARTITION BY repo_id) AS contributors
                FROM author_totals
            )
            SELECT r.repo_name,
                   a.name AS top_author,
                   ranked.commits AS top_author_commits,
                   ranked.total,
                   ranked.contributors,
                   ROUND(100.0 * ranked.commits / ranked.total, 1) AS top_share
            FROM ranked
            JOIN repos   r ON r.repo_id   = ranked.repo_id
            JOIN authors a ON a.author_id = ranked.author_id
            WHERE ranked.rn = 1
            ORDER BY ranked.total DESC
            LIMIT ?
        """, (top_n,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def print_ranking_report(per_repo=3, repo_limit=10):
    """
    Prints the top contributors within each repository followed by the
    concentration measure. This is what main.py calls for this feature.
    """
    connection = get_connection()
    loaded = has_data(connection)
    connection.close()

    if not loaded:
        print("\nNo data found. Choose the load option first.")
        return

    if not window_functions_supported():
        print(f"\nThis feature needs SQLite 3.25 or later for window "
              f"functions. The bundled version is "
              f"{sqlite3.sqlite_version}.")
        return

    results = get_top_contributors_per_repo(per_repo, repo_limit)

    print(f"\nTop {per_repo} Contributors Within Each Repository (SQLite):")
    if not results:
        print("  No commit data to rank.")
        return

    current_repo = None
    for record in results:
        if record["repo_name"] != current_repo:
            current_repo = record["repo_name"]
            print(f"\n  {current_repo}  "
                  f"({record['repo_total']:,} commits total)")
        print(f"    {record['rank_in_repo']}. "
              f"{record['author_name'][:28]:<28} "
              f"{record['commits']:>7,} commits "
              f"({record['pct_of_repo']:>5}%)")

    print("\n\nContribution Concentration:")
    print(f"  {'Repository':<28} {'Top Contributor':<24} "
          f"{'Share':>7} {'People':>8}")
    print("  " + "-" * 70)
    for record in get_contribution_concentration(10):
        print(f"  {record['repo_name'][:28]:<28} "
              f"{record['top_author'][:24]:<24} "
              f"{record['top_share']:>6}% "
              f"{record['contributors']:>8,}")


if __name__ == "__main__":
    print_ranking_report()
