"""
feature_repo_names.py

Feature 3: analyzes repository naming across the dataset, reporting the
longest and shortest repository names and the average name length.

The name length is computed at load time and stored on each document,
so the longest and shortest lookups are indexed sorts rather than full
collection scans. The average is calculated with a $group aggregation
using $avg, $min, and $max, which run on the server rather than
requiring every document to be pulled back into Python.
"""

from mongo_config import get_database, REPOS_COLLECTION


def get_name_stats():
    """
    Returns a dictionary with the average, minimum, and maximum
    repository name lengths across the whole collection.
    """
    db = get_database()

    pipeline = [
        {"$group": {
            "_id": None,
            "avg_length": {"$avg": "$name_length"},
            "min_length": {"$min": "$name_length"},
            "max_length": {"$max": "$name_length"},
            "total": {"$sum": 1},
        }}
    ]

    results = list(db[REPOS_COLLECTION].aggregate(pipeline))
    return results[0] if results else None


def get_longest_names(top_n=5):
    """
    Returns the repositories with the longest names as a list of
    (repo_name, length) tuples.
    """
    db = get_database()
    cursor = db[REPOS_COLLECTION].find().sort("name_length", -1).limit(top_n)
    return [(doc["repo_name"], doc["name_length"]) for doc in cursor]


def get_shortest_names(top_n=5):
    """
    Returns the repositories with the shortest names as a list of
    (repo_name, length) tuples.
    """
    db = get_database()
    cursor = db[REPOS_COLLECTION].find().sort("name_length", 1).limit(top_n)
    return [(doc["repo_name"], doc["name_length"]) for doc in cursor]


def print_name_report(top_n=5):
    """
    Prints the naming statistics along with the longest and shortest
    repository names. This is what main.py calls for this feature.
    """
    stats = get_name_stats()

    if not stats:
        print("\nNo data found. Has the data been loaded yet?")
        return

    print("\nRepository Name Analysis:")
    print(f"  Repositories analyzed: {stats['total']:,}")
    print(f"  Average name length:   {stats['avg_length']:.1f} characters")
    print(f"  Shortest name length:  {stats['min_length']} characters")
    print(f"  Longest name length:   {stats['max_length']} characters")

    print(f"\n  {top_n} Longest Repository Names:")
    for rank, (name, length) in enumerate(get_longest_names(top_n), 1):
        print(f"    {rank}. {name} ({length} chars)")

    print(f"\n  {top_n} Shortest Repository Names:")
    for rank, (name, length) in enumerate(get_shortest_names(top_n), 1):
        print(f"    {rank}. {name} ({length} chars)")


if __name__ == "__main__":
    print_name_report()
