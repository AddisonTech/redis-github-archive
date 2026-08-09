"""
feature_watch_distribution.py

Feature 2: shows how repositories in the dataset are distributed across
watch count ranges, and lists the most watched repositories.

The distribution uses MongoDB's $bucket aggregation stage, which sorts
documents into predefined numeric ranges and counts them, all on the
server. This is a good demonstration of why the aggregation framework
matters: producing this histogram in the Redis version would have meant
either reading every repo back into Python or maintaining a separate
counter for every bucket during loading.
"""

from mongo_config import get_database, REPOS_COLLECTION

# Bucket boundaries. Repository watch counts are heavily skewed, with
# most repos having very few watchers and a handful having tens of
# thousands, so the ranges widen as they go up.
BUCKET_BOUNDARIES = [0, 1, 10, 100, 1000, 10000, 1000000]

BUCKET_LABELS = {
    0: "0 watchers",
    1: "1 to 9",
    10: "10 to 99",
    100: "100 to 999",
    1000: "1,000 to 9,999",
    10000: "10,000+",
}


def get_watch_distribution():
    """
    Returns a list of (label, count) tuples showing how many repos fall
    into each watch count range.
    """
    db = get_database()

    pipeline = [
        {"$bucket": {
            "groupBy": "$watch_count",
            "boundaries": BUCKET_BOUNDARIES,
            "default": "other",
            "output": {"count": {"$sum": 1}},
        }}
    ]

    results = db[REPOS_COLLECTION].aggregate(pipeline)
    return [(BUCKET_LABELS.get(doc["_id"], str(doc["_id"])), doc["count"])
            for doc in results]


def get_most_watched(top_n=10):
    """
    Returns the most watched repositories as a list of
    (repo_name, watch_count) tuples. This is a simple indexed sort
    rather than an aggregation, since the loader created a descending
    index on watch_count.
    """
    db = get_database()
    cursor = db[REPOS_COLLECTION].find().sort("watch_count", -1).limit(top_n)
    return [(doc["repo_name"], doc["watch_count"]) for doc in cursor]


def print_watch_report(top_n=10):
    """
    Prints the distribution histogram followed by the most watched
    repositories. This is what main.py calls for this feature.
    """
    distribution = get_watch_distribution()

    print("\nRepository Distribution by Watch Count:")
    if not distribution:
        print("  No data found. Has the data been loaded yet?")
        return

    max_count = max(count for _, count in distribution)
    for label, count in distribution:
        bar_length = int((count / max_count) * 35) if max_count else 0
        print(f"  {label:<16} {'#' * bar_length} ({count:,} repos)")

    print(f"\nTop {top_n} Most Watched Repositories:")
    for rank, (repo_name, watch_count) in enumerate(get_most_watched(top_n), 1):
        print(f"  {rank:>2}. {repo_name[:45]:<45} {watch_count:,} watchers")


if __name__ == "__main__":
    print_watch_report()
