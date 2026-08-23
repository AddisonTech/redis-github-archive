"""
feature_neo4j_degrees_of_separation.py

Neo4j feature 3: degrees of separation between two contributors.

This finds the shortest chain of shared repositories connecting one
author to another, the same idea as six degrees of separation applied to
the contributor network in the GitHub Archive data.

Why this feature is here
------------------------
Of everything built across the four parts of this project, this is the
one query that has no reasonable implementation in any of the other
three databases. Redis, MongoDB, and Cassandra can all be made to answer
"who worked on this repository" quickly. None of them can answer "what
is the shortest chain of collaborators between these two people"
without pulling the graph into the application and running a traversal
in Python, because the number of hops is not known in advance and each
hop depends on the results of the last one.

Neo4j answers it with shortestPath(), which runs a bidirectional
breadth-first search inside the database and returns the path itself
rather than a set of rows to reassemble.

A modeling decision worth explaining
------------------------------------
The obvious way to build this would be an (Author)-[:COLLABORATED_WITH]-
(Author) relationship created during loading. That was rejected. A
repository with n contributors would need n * (n - 1) / 2 relationships
to connect all of them, so a single repository with two thousand
contributors would add roughly two million edges on its own, for a
graph that is no more expressive than what already exists.

Instead the search runs over the bipartite author-to-repo structure that
is already there, alternating Author, Repo, Author, Repo. Each
collaboration step is two hops rather than one, which is why the path
length is halved when it is reported as a degree of separation.

Uses Sample_Commits.json by way of the CONTRIBUTED_TO relationships.
"""

from neo4j_config import get_session

# Cap on path length, counted in raw hops. Twelve hops is six degrees of
# separation, since each degree is an author-to-repo-to-author step.
# The cap matters: an uncapped variable length pattern on a well
# connected graph can explore an enormous amount of it before deciding
# no path exists.
MAX_HOPS = 12


def list_sample_authors(limit=10):
    """
    Returns authors with the most repository contributions, as a
    convenient starting point for someone trying the feature out.
    """
    with get_session() as session:
        result = session.run("""
            MATCH (a:Author)-[:CONTRIBUTED_TO]->(r:Repo)
            RETURN a.name AS name, count(r) AS repos
            ORDER BY repos DESC, name
            LIMIT $limit
        """, limit=limit)
        return [(record["name"], record["repos"]) for record in result]


def find_path(author_one, author_two):
    """
    Returns the shortest connection between two authors as a list of
    node names alternating author and repository, or None if no path
    exists within MAX_HOPS.

    Both endpoints are matched by exact lowercased name so the lookup
    uses the Author.name constraint's index. shortestPath then searches
    from both ends at once and stops as soon as the two frontiers meet.
    """
    with get_session() as session:
        result = session.run(f"""
            MATCH (a1:Author), (a2:Author)
            WHERE toLower(a1.name) = toLower($author_one)
              AND toLower(a2.name) = toLower($author_two)
            MATCH path = shortestPath(
                (a1)-[:CONTRIBUTED_TO*..{MAX_HOPS}]-(a2))
            RETURN [node IN nodes(path) |
                     coalesce(node.name, 'unknown')] AS names,
                   length(path) AS hops
        """, author_one=author_one, author_two=author_two).single()

        if not result:
            return None
        return {"names": result["names"], "hops": result["hops"]}


def print_path_report(author_one, author_two):
    """
    Prints the chain connecting two authors, or explains why no chain
    was found. This is what main.py calls for this feature.
    """
    if author_one.strip().lower() == author_two.strip().lower():
        print("\nThose are the same author.")
        return

    result = find_path(author_one, author_two)

    print(f"\nConnection from {author_one} to {author_two} (Neo4j):")
    if not result:
        print(f"  No connection found within {MAX_HOPS // 2} degrees. Either "
              f"one of the names is not in the loaded data, or the two "
              f"contributors have no chain of shared repositories between "
              f"them.")
        return

    names = result["names"]
    degrees = result["hops"] // 2

    print(f"  {degrees} degree(s) of separation:\n")
    for position, name in enumerate(names):
        # Even positions are authors, odd positions are the repositories
        # linking them, because the path alternates between the two.
        is_author = position % 2 == 0
        label = "author" if is_author else "via repo"
        # The indent steps in to show the chain, but is capped so a long
        # path does not run off the right side of the terminal.
        indent = "  " * min(position, 8)
        print(f"  {indent}{label}: {name}")


if __name__ == "__main__":
    authors = list_sample_authors(5)
    if len(authors) >= 2:
        print("Authors with the most repository contributions:")
        for name, repos in authors:
            print(f"  {name} ({repos} repos)")
        print_path_report(authors[0][0], authors[-1][0])
    else:
        print("Not enough data loaded, run neo4j_data_loader.py first")
