"""
feature_language_stats.py

Feature 1: shows the most popular programming languages across the
entire dataset, ranked by total bytes of code, using the
languages:ranked sorted set that data_loader.py builds from
Languages.json.
"""

from redis_config import get_redis_connection


def get_top_languages(top_n=10):
    """
    Returns the top_n languages as a list of (name, total_bytes)
    tuples, highest first, using Redis's ZREVRANGE with scores.
    """
    r = get_redis_connection()
    results = r.zrevrange("languages:ranked", 0, top_n - 1, withscores=True)
    return [(name, int(score)) for name, score in results]


def print_language_report(top_n=10):
    results = get_top_languages(top_n)
    print(f"\nTop {top_n} Languages by Total Bytes:")
    if not results:
        print("  No data found. Has data_loader.py been run yet?")
        return
    for rank, (language, total_bytes) in enumerate(results, start=1):
        print(f"  {rank}. {language}: {total_bytes:,} bytes")


if __name__ == "__main__":
    print_language_report()
