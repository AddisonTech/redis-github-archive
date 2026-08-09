"""
feature_commit_activity.py

Feature 2: visualizes commit activity for a chosen repository, showing
which authors have contributed the most commits. Built from the
commits:by_author:<repo_name> sorted set that data_loader.py builds
while loading Sample_Commits.json.

Note: this dataset doesn't include commit timestamps, so "commit
history" here means commit activity by author rather than activity
over time.
"""

from redis_config import get_redis_connection

# Uncomment if you want a real chart instead of the text bar version:
import matplotlib.pyplot as plt


def list_available_repos():
    """
    Returns the list of repo names that have commit data loaded, so the
    user knows what they can choose from.
    """
    r = get_redis_connection()
    return sorted(r.smembers("repos:loaded"))


def get_commit_activity(repo_name, top_n=10):
    """
    Returns the top_n authors for repo_name as a list of
    (author_name, commit_count) tuples, highest first.
    """
    r = get_redis_connection()
    key = f"commits:by_author:{repo_name}"
    results = r.zrevrange(key, 0, top_n - 1, withscores=True)
    return [(author, int(score)) for author, score in results]


def show_commit_activity(repo_name, top_n=10):
    """
    Displays commit activity for repo_name as a text bar chart. This is
    what main.py calls when the user picks this feature from the menu.
    """
    data = get_commit_activity(repo_name, top_n)

    if not data:
        print(f"No commit data found for {repo_name}.")
        available = list_available_repos()
        print("Available repos:", ", ".join(available) if available else "none loaded yet")
        return

    print(f"\nTop Contributors to {repo_name}:")
    max_count = data[0][1]
    for author, count in data:
        bar_length = int((count / max_count) * 40) if max_count else 0
        print(f"  {author[:25]:<25} {'#' * bar_length} ({count})")

    # TODO if you want a real chart instead of text bars:
    names = [d[0] for d in data]
    counts = [d[1] for d in data]
    plt.barh(names, counts)
    plt.xlabel("Commits")
    plt.title(f"Top Contributors to {repo_name}")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    repos = list_available_repos()
    print("Available repos:", ", ".join(repos) if repos else "none loaded yet, run data_loader.py first")
    if repos:
        show_commit_activity(repos[0])
