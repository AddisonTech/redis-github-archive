"""
feature_license_stats.py

Feature 3: shows the most common software licenses across the repos in
Licenses.json, using the licenses:ranked sorted set that data_loader.py
builds while loading that file.
"""

from redis_config import get_redis_connection


def get_top_licenses(top_n=10):
    """
    Returns the top_n licenses as a list of (name, repo_count) tuples,
    highest first.
    """
    r = get_redis_connection()
    results = r.zrevrange("licenses:ranked", 0, top_n - 1, withscores=True)
    return [(name, int(score)) for name, score in results]


def print_license_report(top_n=10):
    results = get_top_licenses(top_n)
    print(f"\nTop {top_n} Licenses by Repo Count:")
    if not results:
        print("  No data found. Has data_loader.py been run yet?")
        return
    for rank, (license_name, count) in enumerate(results, start=1):
        print(f"  {rank}. {license_name}: {count} repos")


if __name__ == "__main__":
    print_license_report()
