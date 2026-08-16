"""
feature_cassandra_licenses.py

Cassandra feature 3: the most common open source licenses across the
repositories in the dataset.

This reads license_counts, a counter table built while loading
Licenses.json. Every license column lives under one partition key value
because the number of distinct licenses is small and the feature always
wants all of them at once. Splitting them across partitions would turn
one node-local read into a fan-out across the cluster for no benefit.

The query is issued with an explicit consistency level rather than
relying on the driver default. Consistency in Cassandra is a per-query
decision, not a database-wide setting, which is a genuine difference
from the other two databases in this project. ONE returns as soon as a
single replica answers, which is the right call for a read-only
popularity report where a slightly stale count changes nothing. A CRUD
delete in cassandra_crud.py uses QUORUM instead, because there the
answer has to be correct rather than fast.

Uses Licenses.json.
"""

from cassandra.query import SimpleStatement, ConsistencyLevel
from cassandra_config import get_session, GLOBAL_BUCKET


def get_top_licenses(top_n=10):
    """
    Returns the top_n licenses as a list of (license_name, repo_count)
    tuples, most used first.

    Counters cannot be clustering columns, so Cassandra will not return
    this partition pre-sorted the way repos_by_watch_tier is. The
    partition holds one row per distinct license, which is a few dozen
    rows, so ranking them in the application costs nothing here.
    """
    session = get_session()

    statement = SimpleStatement(
        "SELECT license_name, repo_count FROM license_counts "
        "WHERE bucket = %s",
        consistency_level=ConsistencyLevel.ONE)

    result = session.execute(statement, (GLOBAL_BUCKET,))
    licenses = [(row.license_name, row.repo_count) for row in result
                if row.repo_count and row.repo_count > 0]
    licenses.sort(key=lambda pair: pair[1], reverse=True)
    return licenses[:top_n]


def print_license_report(top_n=10):
    """
    Prints license popularity as a ranked list with a text bar chart
    and each license's share of the dataset. This is what main.py calls
    for this feature.
    """
    results = get_top_licenses(top_n)

    print(f"\nTop {top_n} Licenses by Repository Count (Cassandra):")
    if not results:
        print("  No data found. Has the data been loaded yet?")
        return

    max_count = results[0][1]
    total = sum(count for _, count in results)

    for rank, (license_name, count) in enumerate(results, start=1):
        bar_length = int((count / max_count) * 30) if max_count else 0
        share = (count / total * 100) if total else 0
        print(f"  {rank:>2}. {license_name[:20]:<20} {'#' * bar_length} "
              f"({count:,} repos, {share:.1f}%)")


if __name__ == "__main__":
    print_license_report()
