"""
feature_commit_viz.py
OWNER: Person 4

Purpose: This is Feature 2 of the three required features. Visualizes
the commit/push history for a repository using the event data stored
in Redis, for example a simple bar chart of pushes per day, or per
repo.

You'll need data loaded by Person 1 before this returns real results.

TODO:
    - Decide exactly what to visualize (commits per day is the
      simplest option that still satisfies the rubric).
    - Pull the relevant timestamps/counts from Redis.
    - Build the chart with matplotlib (already listed in
      requirements.txt) or print an ASCII-style bar chart to the
      console if you'd rather skip the extra dependency.
"""

from collections import Counter
from redis_config import get_redis_connection

# Uncomment if using matplotlib for the visualization:
# import matplotlib.pyplot as plt


def get_commit_counts_by_day(repo_name=None):
    """
    Returns a dictionary of date -> commit count, optionally filtered
    to a single repo_name. If repo_name is None, aggregates across
    all repos in the dataset.

    TODO: implement using the event data and timestamps Person 1
    stored. Group by date (e.g. event["created_at"][:10]) and tally
    with collections.Counter.
    """
    r = get_redis_connection()
    counts = Counter()

    # TODO: replace with real logic once the schema is finalized.
    # for event_id in r.smembers("events:by_type:PushEvent"):
    #     event = r.hgetall(f"event:{event_id}")
    #     if repo_name and event.get("repo_name") != repo_name:
    #         continue
    #     day = event.get("created_at", "")[:10]
    #     if day:
    #         counts[day] += 1

    return dict(sorted(counts.items()))


def show_commit_history(repo_name=None):
    """
    Displays the commit history, either as a matplotlib chart or a
    simple text report. This is what main.py will call when the user
    picks this feature from the menu.
    """
    data = get_commit_counts_by_day(repo_name)

    if not data:
        print("No commit data found. Has data_loader.py been run yet?")
        return

    print(f"\nCommit History{' for ' + repo_name if repo_name else ''}:")
    for day, count in data.items():
        print(f"  {day}: {'#' * count} ({count})")

    # TODO: swap the text output above for a matplotlib bar chart if
    # you want a visual, something like:
    # plt.bar(data.keys(), data.values())
    # plt.xticks(rotation=45)
    # plt.xlabel("Date")
    # plt.ylabel("Commits")
    # plt.title("Commit History")
    # plt.tight_layout()
    # plt.show()


if __name__ == "__main__":
    # Lets Person 4 test this file on its own without running main.py
    show_commit_history()
