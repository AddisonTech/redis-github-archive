"""
feature_neo4j_repo_similarity.py

Neo4j feature 2: similarity between repositories based on shared
contributors.

Two repositories are treated as similar when the same people work on
both. The query walks from one repository, out through its contributors,
and back down into every other repository those people touched:

    (r1:Repo)<-[:CONTRIBUTED_TO]-(a:Author)-[:CONTRIBUTED_TO]->(r2:Repo)

That is a two hop traversal, and it is worth being precise about why it
matters. The path never touches a repository that has no connection to
the starting one. Neo4j follows relationships out from a known node, so
the work is proportional to how connected that node is, not to how many
repositories exist in the database. A document or column-family store
answering the same question has to consider the whole collection and
filter down.

Similarity is scored two ways, because raw overlap is misleading on its
own. A repository with thousands of contributors will share people with
almost everything simply by being large. The Jaccard index corrects for
that by dividing the contributors the two repositories share by the
total distinct contributors across both, so a small repository whose
entire team also works on another one scores higher than a large one
with an incidental overlap.

Uses Sample_Commits.json by way of the CONTRIBUTED_TO relationships and
Sample_Repos.json for the watch counts shown alongside the results.
"""

from neo4j_config import get_session


def list_repos_with_contributors(limit=25):
    """
    Returns repositories that have contributors in the graph, so the
    menu can show the user valid choices.
    """
    with get_session() as session:
        result = session.run("""
            MATCH (:Author)-[:CONTRIBUTED_TO]->(r:Repo)
            RETURN r.name AS name, count(*) AS contributors
            ORDER BY contributors DESC
            LIMIT $limit
        """, limit=limit)
        return [(record["name"], record["contributors"]) for record in result]


def get_similar_repos(repo_name, top_n=10):
    """
    Returns repositories most similar to repo_name, as a list of
    dictionaries with the shared contributor count, the Jaccard index,
    and a few of the contributor names in common.

    The size of each repository's contributor set is counted first so
    the Jaccard denominator can be built without a second pass over the
    graph. Shared contributors are subtracted once from the sum of both
    sets, since counting them in each set would double them in the
    union.
    """
    with get_session() as session:
        result = session.run("""
            MATCH (r1:Repo)
            WHERE toLower(r1.name) = toLower($repo_name)
            MATCH (r1)<-[:CONTRIBUTED_TO]-(:Author)
            WITH r1, count(*) AS r1_contributors

            MATCH (r1)<-[:CONTRIBUTED_TO]-(a:Author)-[:CONTRIBUTED_TO]->(r2:Repo)
            WHERE r2 <> r1
            WITH r1, r1_contributors, r2,
                 count(DISTINCT a) AS shared,
                 collect(DISTINCT a.name)[0..3] AS sample_authors

            MATCH (r2)<-[:CONTRIBUTED_TO]-(:Author)
            WITH r1_contributors, r2, shared, sample_authors,
                 count(*) AS r2_contributors

            RETURN r2.name AS repo_name,
                   shared,
                   r2_contributors,
                   sample_authors,
                   coalesce(r2.watch_count, 0) AS watch_count,
                   toFloat(shared) /
                     (r1_contributors + r2_contributors - shared) AS jaccard
            ORDER BY jaccard DESC, shared DESC
            LIMIT $top_n
        """, repo_name=repo_name, top_n=top_n)
        return [dict(record) for record in result]


def print_similarity_report(repo_name, top_n=10):
    """
    Prints the repositories most similar to repo_name. This is what
    main.py calls for this feature.
    """
    results = get_similar_repos(repo_name, top_n)

    print(f"\nRepositories Similar to {repo_name} (Neo4j):")
    if not results:
        print("  No similar repositories found. Either the name does not "
              "match a loaded repository, or none of its contributors "
              "worked on anything else in the dataset.")
        return

    print(f"  {'Repository':<38} {'Shared':>7} {'Jaccard':>9}  Sample")
    for record in results:
        sample = ", ".join(record["sample_authors"][:2])
        print(f"  {record['repo_name'][:38]:<38} "
              f"{record['shared']:>7} "
              f"{record['jaccard']:>9.3f}  {sample[:30]}")


if __name__ == "__main__":
    repos = list_repos_with_contributors(5)
    if repos:
        print("Repositories with the most contributors:")
        for name, contributors in repos:
            print(f"  {name} ({contributors} contributors)")
        print_similarity_report(repos[0][0])
    else:
        print("No data loaded yet, run neo4j_data_loader.py first")
