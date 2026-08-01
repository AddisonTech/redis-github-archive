"""
feature_language_stats.py
OWNER: Person 3

Purpose: This is Feature 1 of the three required features. Analyzes the
GitHub Archive event data stored in Redis to show which programming
languages or technologies appear most often.

You'll need data loaded by Person 1 before this will return real
results, so coordinate on the schema and test with a small sample once
data_loader.py is working.

TODO:
    - Decide what "popularity" means for your feature. Options include
      counting PushEvents per repo language, or counting how many
      events mention a given language in repo names or descriptions.
    - Implement the counting logic below using the Redis keys Person 1
      set up.
    - Decide how to present the results (sorted list printed to the
      console is fine, a bar chart is a nice bonus).
"""

from collections import Counter
from redis_config import get_redis_connection


def analyze_language_popularity(top_n=10):
    """
    Scans the event data in Redis and returns the top_n most common
    languages/technologies as a list of (name, count) tuples, sorted
    from most to least common.

    TODO: implement. A rough approach:
        1. Get the set of all event ids (or iterate by type if that's
           more efficient given the schema).
        2. Pull the language field from each event hash.
        3. Tally with collections.Counter.
        4. Return Counter.most_common(top_n).
    """
    r = get_redis_connection()
    counts = Counter()

    # TODO: replace this placeholder loop with real logic once the
    # schema is finalized.
    # for event_id in r.smembers("events:by_type:PushEvent"):
    #     event = r.hgetall(f"event:{event_id}")
    #     language = event.get("language")
    #     if language:
    #         counts[language] += 1

    return counts.most_common(top_n)


def print_language_report(top_n=10):
    """
    Prints a simple ranked report to the console. This is what
    main.py will call when the user picks this feature from the menu.
    """
    results = analyze_language_popularity(top_n)
    print(f"\nTop {top_n} Languages/Technologies:")
    if not results:
        print("  No data found. Has data_loader.py been run yet?")
        return
    for rank, (language, count) in enumerate(results, start=1):
        print(f"  {rank}. {language}: {count} events")


if __name__ == "__main__":
    # Lets Person 3 test this file on its own without running main.py
    print_language_report()
