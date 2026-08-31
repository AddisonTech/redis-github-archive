"""
feature_sqlite_committers.py

SQLite feature 2: how many distinct committers work on each repository,
and how that number is distributed across the dataset.

The interesting part of this feature is that it aggregates an aggregate.
The average number of committers per repository is not a column anywhere
and cannot be computed in a single GROUP BY, because it is the mean of a
count. The query counts committers per repository first, then averages
that result.

Common table expressions are what make that readable. The WITH clause
names an intermediate result and the outer query selects from it as
though it were a table. Without them the same logic becomes a nested
subquery in the FROM clause, which works identically and is much harder
to follow.

None of the four NoSQL databases in this project supports anything of
the sort. MongoDB comes closest, since a pipeline can group twice, but
the stages are a sequence rather than named results that can be
referenced more than once. Redis and Cassandra had to precompute counts
at write time and could not have averaged them without reading
everything back into Python. Neo4j can aggregate but not compose
aggregates this way.

Uses Sample_Commits.json for the commits and Sample_Repos.json for the
watch counts.
"""

import matplotlib.pyplot as plt
from sqlite_config import get_connection, has_data


def get_committer_stats():
    """
    Returns overall statistics about committers per repository: the
    average, minimum, maximum, and the number of repositories counted.

    The CTE produces one row per repository holding its committer count,
    and the outer query treats those rows as the input to a second round
    of aggregation.
    """
    connection = get_connection()
    try:
        row = connection.execute("""
            WITH committers_per_repo AS (
                SELECT c.repo_id,
                       COUNT(DISTINCT c.author_id) AS committer_count
                FROM commits c
                GROUP BY c.repo_id
            )
            SELECT COUNT(*)                    AS repos_counted,
                   ROUND(AVG(committer_count), 2) AS avg_committers,
                   MIN(committer_count)        AS min_committers,
                   MAX(committer_count)        AS max_committers,
                   SUM(committer_count)        AS total_committer_links
            FROM committers_per_repo
        """).fetchone()
        return dict(row) if row and row["repos_counted"] else None
    finally:
        connection.close()


def get_committers_by_repo(top_n=15):
    """
    Returns committer and commit counts per repository, alongside the
    watch count, ordered by how many distinct people contributed.

    The ratio of commits to committers at the end is a small thing that
    says something real about a project: a high number means a few
    people doing most of the work, a low one means the effort is spread
    across many contributors.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT r.repo_name,
                   r.watch_count,
                   COUNT(DISTINCT c.author_id) AS committers,
                   COUNT(*)                    AS commits,
                   ROUND(CAST(COUNT(*) AS REAL) /
                         COUNT(DISTINCT c.author_id), 1) AS commits_per_person
            FROM commits c
            JOIN repos r ON r.repo_id = c.repo_id
            GROUP BY r.repo_id
            ORDER BY committers DESC
            LIMIT ?
        """, (top_n,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_committer_distribution():
    """
    Returns how many repositories fall into each committer count band.

    The CASE expression assigns each repository to a band, and the outer
    query counts the bands. This is the same histogram the MongoDB part
    built with $bucket and the Cassandra part built with counter tables
    maintained during loading. Here it is an expression in the query,
    computed on demand with nothing prepared in advance.
    """
    connection = get_connection()
    try:
        rows = connection.execute("""
            WITH committers_per_repo AS (
                SELECT repo_id, COUNT(DISTINCT author_id) AS n
                FROM commits
                GROUP BY repo_id
            )
            SELECT CASE
                     WHEN n = 1        THEN '1 committer'
                     WHEN n BETWEEN 2 AND 5   THEN '2 to 5'
                     WHEN n BETWEEN 6 AND 20  THEN '6 to 20'
                     WHEN n BETWEEN 21 AND 100 THEN '21 to 100'
                     ELSE '100+'
                   END AS band,
                   COUNT(*) AS repo_count,
                   MIN(n)   AS band_min
            FROM committers_per_repo
            GROUP BY band
            ORDER BY band_min
        """).fetchall()
        return [(row["band"], row["repo_count"]) for row in rows]
    finally:
        connection.close()


def print_committer_report(top_n=15, show_chart=True):
    """
    Prints the overall statistics, the distribution histogram, and the
    repositories with the most contributors, then renders a chart. This
    is what main.py calls for this feature.
    """
    connection = get_connection()
    loaded = has_data(connection)
    connection.close()

    if not loaded:
        print("\nNo data found. Choose the load option first.")
        return

    stats = get_committer_stats()
    if not stats:
        print("\nNo commit data to analyze.")
        return

    print("\nCommitters per Repository (SQLite):")
    print(f"  Repositories analyzed:      {stats['repos_counted']:,}")
    print(f"  Average committers per repo: {stats['avg_committers']}")
    print(f"  Fewest committers:           {stats['min_committers']}")
    print(f"  Most committers:             {stats['max_committers']}")

    distribution = get_committer_distribution()
    if distribution:
        print("\n  Distribution:")
        max_count = max(count for _, count in distribution)
        for band, count in distribution:
            bar = "#" * int((count / max_count) * 30) if max_count else ""
            print(f"    {band:<14} {bar} ({count:,} repos)")

    results = get_committers_by_repo(top_n)
    print("\n  Repositories with the Most Contributors:")
    print(f"    {'Repository':<30} {'People':>7} {'Commits':>9} {'Per Person':>11}")
    print("    " + "-" * 60)
    for record in results:
        print(f"    {record['repo_name'][:30]:<30} "
              f"{record['committers']:>7,} "
              f"{record['commits']:>9,} "
              f"{record['commits_per_person']:>11}")

    if show_chart and results:
        names = [record["repo_name"][:22] for record in results[:10]]
        counts = [record["committers"] for record in results[:10]]
        plt.barh(names, counts)
        plt.xlabel("Distinct committers")
        plt.title("Committers per Repository")
        plt.gca().invert_yaxis()
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    print_committer_report(show_chart=False)
