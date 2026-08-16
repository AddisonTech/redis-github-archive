"""
feature_cassandra_commit_activity.py

Cassandra feature 1: top contributors for a chosen repository.

This reads commit_counts_by_author, a counter table that
cassandra_data_loader.py maintains while loading Sample_Commits.json.
Every commit increments its author's counter on the way in, so the
count already exists by the time anyone asks for it.

That design is forced by Cassandra rather than chosen for convenience.
There is no GROUP BY, no COUNT over an arbitrary column, and no
aggregation pipeline, so a count either happens at write time or does
not happen at all without dragging the data back into the application.

One honest limitation shows up here: a counter cannot be a clustering
column, so Cassandra will not sort the partition by commit_count. The
read pulls the whole partition, which is bounded by the number of
distinct authors on one repository, and ranks it in Python. The
comparable MongoDB feature does its sorting on the server. This is a
real trade-off, not an oversight, and the fix in a production system
would be a second table keyed by count.

Uses Sample_Commits.json. The dataset has no commit timestamps, so
activity is reported by author rather than over time.
"""

import matplotlib.pyplot as plt
from cassandra_config import get_session, GLOBAL_BUCKET


def list_available_repos():
    """
    Returns repository names that have commit data loaded, read from
    the repos_loaded table.
    """
    session = get_session()
    result = session.execute(
        "SELECT repo_name FROM repos_loaded WHERE bucket = %s",
        (GLOBAL_BUCKET,))
    return sorted(row.repo_name for row in result)


def get_commit_activity(repo_name, top_n=10):
    """
    Returns the top_n authors for repo_name as a list of
    (author_name, commit_count) tuples, highest first.

    The WHERE clause hits the partition key exactly, so this is a
    single partition read on a single node, no ALLOW FILTERING and no
    coordinator fan-out.
    """
    session = get_session()
    result = session.execute("""
        SELECT author_name, commit_count
        FROM commit_counts_by_author
        WHERE repo_name = %s
    """, (repo_name,))

    authors = [(row.author_name, row.commit_count) for row in result
               if row.commit_count and row.commit_count > 0]
    authors.sort(key=lambda pair: pair[1], reverse=True)
    return authors[:top_n]


def show_commit_activity(repo_name, top_n=10, show_chart=True):
    """
    Prints commit activity for repo_name as a text bar chart and then
    renders the same data as a matplotlib chart. This is what main.py
    calls for this feature.
    """
    data = get_commit_activity(repo_name, top_n)

    if not data:
        print(f"\nNo commit data found for {repo_name}.")
        available = list_available_repos()
        print("Available repos:",
              ", ".join(available) if available else "none loaded yet")
        return

    print(f"\nTop Contributors to {repo_name} (Cassandra):")
    max_count = data[0][1]
    for author, count in data:
        bar_length = int((count / max_count) * 40) if max_count else 0
        print(f"  {author[:25]:<25} {'#' * bar_length} ({count:,})")

    if show_chart:
        names = [pair[0] for pair in data]
        counts = [pair[1] for pair in data]
        plt.barh(names, counts)
        plt.xlabel("Commits")
        plt.title(f"Top Contributors to {repo_name}")
        plt.gca().invert_yaxis()  # highest count at the top
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    repos = list_available_repos()
    print("Available repos:", ", ".join(repos) if repos
          else "none loaded yet, run cassandra_data_loader.py first")
    if repos:
        show_commit_activity(repos[0])
