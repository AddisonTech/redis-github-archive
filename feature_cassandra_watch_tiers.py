"""
feature_cassandra_watch_tiers.py

Cassandra feature 2: how repositories are distributed across watch
count tiers, plus the most watched repositories inside any tier.

This feature exists to demonstrate clustering columns, which are the
part of Cassandra data modeling that has no equivalent in Redis or
MongoDB. repos_by_watch_tier is declared as:

    PRIMARY KEY ((watch_tier), watch_count, repo_name)
    WITH CLUSTERING ORDER BY (watch_count DESC, repo_name ASC)

watch_tier is the partition key, so a query for one tier lands on one
node. watch_count is a clustering column in descending order, which
means rows are physically stored on disk already sorted by watch count.
Asking for the top ten repositories in a tier is a sequential read of
the first ten rows in the partition. Nothing is sorted at query time and
nothing is sorted in Python.

The histogram itself comes from repo_counts_by_tier, a counter table
built during loading, for the same reason the author counters exist:
Cassandra will not count rows for you across a table without scanning it.

Uses Sample_Repos.json.
"""

from cassandra_config import get_session, GLOBAL_BUCKET
from cassandra_data_loader import TIER_ORDER


def get_watch_distribution():
    """
    Returns a list of (tier_label, repo_count) tuples in tier order,
    read from the counter table maintained during loading.
    """
    session = get_session()
    result = session.execute(
        "SELECT watch_tier, repo_count FROM repo_counts_by_tier "
        "WHERE bucket = %s", (GLOBAL_BUCKET,))

    counts = {row.watch_tier: row.repo_count for row in result}
    return [(tier, counts.get(tier, 0)) for tier in TIER_ORDER]


def get_most_watched_in_tier(tier, top_n=10):
    """
    Returns the most watched repositories inside one tier as a list of
    (repo_name, watch_count) tuples.

    No ORDER BY is needed. The clustering order on the table already
    stores these rows highest first, so LIMIT alone gives the top N.
    """
    session = get_session()
    result = session.execute(
        "SELECT repo_name, watch_count FROM repos_by_watch_tier "
        "WHERE watch_tier = %s LIMIT %s", (tier, top_n))
    return [(row.repo_name, row.watch_count) for row in result]


def get_most_watched_overall(top_n=10):
    """
    Returns the most watched repositories in the dataset by reading the
    highest tiers in order until top_n rows have been collected.

    A single query cannot span partitions in sorted order, since sort
    order only exists inside a partition. Walking the tiers from the
    top down is the standard way around that, and it works here because
    the tier boundaries are themselves ordered.
    """
    collected = []
    for tier in reversed(TIER_ORDER):
        if len(collected) >= top_n:
            break
        collected.extend(get_most_watched_in_tier(tier, top_n - len(collected)))
    return collected[:top_n]


def print_watch_report(top_n=10):
    """
    Prints the tier histogram followed by the most watched
    repositories. This is what main.py calls for this feature.
    """
    distribution = get_watch_distribution()

    print("\nRepository Distribution by Watch Count (Cassandra):")
    if not any(count for _, count in distribution):
        print("  No data found. Has the data been loaded yet?")
        return

    max_count = max(count for _, count in distribution)
    for label, count in distribution:
        bar_length = int((count / max_count) * 35) if max_count else 0
        print(f"  {label:<16} {'#' * bar_length} ({count:,} repos)")

    print(f"\nTop {top_n} Most Watched Repositories:")
    for rank, (repo_name, watch_count) in enumerate(
            get_most_watched_overall(top_n), start=1):
        print(f"  {rank:>2}. {repo_name[:45]:<45} {watch_count:,} watchers")


if __name__ == "__main__":
    print_watch_report()
