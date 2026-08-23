"""
feature_neo4j_collaboration.py

Neo4j feature 1: collaboration patterns between authors.

Two authors are treated as collaborators when they have both
contributed to the same repository. The query expresses that directly
as a shape in the graph:

    (a1:Author)-[:CONTRIBUTED_TO]->(r:Repo)<-[:CONTRIBUTED_TO]-(a2:Author)

That pattern is the entire logic of the feature. There is no join, no
grouping key to construct, and no intermediate result set to hold on
to. Neo4j matches the shape by walking relationships from each author
node, which is the thing a graph database does that none of the other
three in this project can.

For contrast, the same question in the earlier parts: MongoDB would
need a self-lookup on the commits collection followed by an unwind and
a group, and would still return author pairs rather than a traversable
structure. Cassandra could not answer it at all without a table built
in advance for exactly this query. Redis would require reading the
membership sets back into Python and intersecting them there.

The WHERE clause comparing author names keeps each pair from being
reported twice, once in each direction, and keeps an author from being
reported as their own collaborator.

Uses Sample_Commits.json by way of the CONTRIBUTED_TO relationships the
loader derives.
"""

from neo4j_config import get_session


def get_top_collaborations(top_n=15):
    """
    Returns the author pairs who share the most repositories, as a list
    of dictionaries with both names, the number of shared repositories,
    and their combined commit count across those repositories.
    """
    with get_session() as session:
        result = session.run("""
            MATCH (a1:Author)-[c1:CONTRIBUTED_TO]->(r:Repo)
                  <-[c2:CONTRIBUTED_TO]-(a2:Author)
            WHERE a1.name < a2.name
            WITH a1, a2,
                 count(DISTINCT r) AS shared_repos,
                 sum(c1.commits + c2.commits) AS combined_commits
            RETURN a1.name AS author_one,
                   a2.name AS author_two,
                   shared_repos,
                   combined_commits
            ORDER BY shared_repos DESC, combined_commits DESC
            LIMIT $top_n
        """, top_n=top_n)
        return [dict(record) for record in result]


def get_collaborators_for(author_name, top_n=10):
    """
    Returns the authors who share the most repositories with one
    specific author.

    Starting the match from a single named node means Neo4j begins at
    one point in the graph and walks outward, rather than evaluating the
    pattern across every author. The constraint on Author.name makes
    that starting lookup an index hit.
    """
    with get_session() as session:
        result = session.run("""
            MATCH (a:Author)-[:CONTRIBUTED_TO]->(r:Repo)
                  <-[c:CONTRIBUTED_TO]-(other:Author)
            WHERE toLower(a.name) = toLower($author_name)
              AND other.name <> a.name
            WITH other,
                 count(DISTINCT r) AS shared_repos,
                 collect(DISTINCT r.name) AS repos,
                 sum(c.commits) AS their_commits
            RETURN other.name AS collaborator,
                   shared_repos,
                   repos,
                   their_commits
            ORDER BY shared_repos DESC, their_commits DESC
            LIMIT $top_n
        """, author_name=author_name, top_n=top_n)
        return [dict(record) for record in result]


def print_collaboration_report(top_n=15):
    """
    Prints the author pairs with the most shared repositories. This is
    what main.py calls for this feature.
    """
    results = get_top_collaborations(top_n)

    print(f"\nTop {top_n} Collaborating Author Pairs (Neo4j):")
    if not results:
        print("  No data found. Has the data been loaded yet?")
        return

    for rank, record in enumerate(results, start=1):
        pair = f"{record['author_one'][:22]} + {record['author_two'][:22]}"
        print(f"  {rank:>2}. {pair:<50} "
              f"{record['shared_repos']} shared repo(s), "
              f"{record['combined_commits']:,} commits")


def print_collaborators_for(author_name, top_n=10):
    """
    Prints the closest collaborators for one named author, along with
    the repositories they share.
    """
    results = get_collaborators_for(author_name, top_n)

    print(f"\nCollaborators of {author_name}:")
    if not results:
        print("  No collaborators found. Check the spelling, or the "
              "author may not be in the loaded data.")
        return

    for rank, record in enumerate(results, start=1):
        repos = ", ".join(record["repos"][:3])
        print(f"  {rank:>2}. {record['collaborator'][:30]:<30} "
              f"{record['shared_repos']} shared ({repos})")


if __name__ == "__main__":
    print_collaboration_report()
