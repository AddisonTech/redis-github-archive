"""
main.py

Entry point for the GitHub Archive database application.

The project supports five databases, one per part of the course
project:

    Part 1  Redis      key-value store       (NoSQL)
    Part 2  MongoDB    document store        (NoSQL)
    Part 3  Cassandra  column-family store   (NoSQL)
    Part 4  Neo4j      graph store           (NoSQL)
    Part 5  SQLite     relational store      (SQL)

All five implementations are kept in the same project rather than
replaced, so the same application can be run against each one and the
differences between the five data models can be compared directly.
That comparison is the point of building the application five times,
and the final part is the only relational one, which is what makes the
comparison worth making.

Run with: python main.py
"""

import cassandra_config
import mongo_config
import neo4j_config
import sqlite_config

# Redis modules from part 1
from data_loader import load_all_data as load_redis_data
from crud_operations import run_crud_menu as run_redis_crud
from feature_language_stats import print_language_report
from feature_license_stats import print_license_report
from feature_commit_activity import (show_commit_activity,
                                     list_available_repos)

# MongoDB modules from part 2
from mongo_data_loader import load_all_data as load_mongo_data
from mongo_crud import run_crud_menu as run_mongo_crud
from feature_commit_words import print_word_report
from feature_watch_distribution import print_watch_report
from feature_repo_names import print_name_report

# Cassandra modules from part 3
from cassandra_data_loader import load_all_data as load_cassandra_data
from cassandra_crud import (run_crud_menu as run_cassandra_crud,
                            list_loaded_repos as list_cassandra_repos)
from feature_cassandra_commit_activity import (
    show_commit_activity as show_cassandra_activity)
from feature_cassandra_watch_tiers import (
    print_watch_report as print_cassandra_watch_report)
from feature_cassandra_licenses import (
    print_license_report as print_cassandra_license_report)

# Neo4j modules from part 4
from neo4j_data_loader import load_all_data as load_neo4j_data
from neo4j_crud import (run_crud_menu as run_neo4j_crud,
                        list_loaded_repos as list_neo4j_repos)
from feature_neo4j_collaboration import (print_collaboration_report,
                                         print_collaborators_for)
from feature_neo4j_repo_similarity import (print_similarity_report,
                                           list_repos_with_contributors)
from feature_neo4j_degrees_of_separation import (print_path_report,
                                                 list_sample_authors)

# SQLite modules from part 5
from sqlite_data_loader import load_all_data as load_sqlite_data
from sqlite_crud import run_crud_menu as run_sqlite_crud
from feature_sqlite_file_activity import print_file_activity_report
from feature_sqlite_committers import print_committer_report
from feature_sqlite_contributor_ranking import print_ranking_report


def sqlite_menu():
    """SQLite section of the application, added in part 5."""
    if not sqlite_config.check_connection():
        print("\nCould not open the SQLite database file. Check that the "
              "project folder is writable.")
        return

    while True:
        print("\n--- SQLite ---")
        print("1. Load data into SQLite")
        print("2. CRUD operations")
        print("3. Feature: File activity in the most watched repos")
        print("4. Feature: Committers per repository")
        print("5. Feature: Top contributors ranked within each repo")
        print("6. Back to main menu")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_sqlite_data("data")
        elif choice == "2":
            run_sqlite_crud()
        elif choice == "3":
            print_file_activity_report()
        elif choice == "4":
            print_committer_report()
        elif choice == "5":
            print_ranking_report()
        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


def neo4j_menu():
    """Neo4j section of the application, added in part 4."""
    if not neo4j_config.check_connection():
        print("\nCould not connect to Neo4j. Make sure the server is "
              "running and the credentials in neo4j_config.py are correct "
              "before using this section.")
        return

    while True:
        print("\n--- Neo4j ---")
        print("1. Load data into Neo4j")
        print("2. CRUD operations")
        print("3. Feature: Collaboration patterns between authors")
        print("4. Feature: Repository similarity by shared contributors")
        print("5. Feature: Degrees of separation between two authors")
        print("6. Back to main menu")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_neo4j_data("data")
        elif choice == "2":
            run_neo4j_crud()
        elif choice == "3":
            print_collaboration_report()
            author = input("\nEnter an author name to see their "
                           "collaborators, or press Enter to skip: ").strip()
            if author:
                print_collaborators_for(author)
        elif choice == "4":
            repos = list_repos_with_contributors(10)
            if not repos:
                print("No data loaded yet.")
                continue
            print("\nRepositories with the most contributors:")
            for name, contributors in repos:
                print(f"  {name} ({contributors} contributors)")
            repo_choice = input("Enter a repo name from the list "
                                "above: ").strip()
            if repo_choice:
                print_similarity_report(repo_choice)
        elif choice == "5":
            authors = list_sample_authors(10)
            if not authors:
                print("No data loaded yet.")
                continue
            print("\nAuthors with the most repository contributions:")
            for name, repos in authors:
                print(f"  {name} ({repos} repos)")
            first = input("First author name: ").strip()
            second = input("Second author name: ").strip()
            if first and second:
                print_path_report(first, second)
        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


def cassandra_menu():
    """Cassandra section of the application, added in part 3."""
    if not cassandra_config.check_connection():
        print("\nCould not connect to Cassandra. Make sure the node is "
              "running and the credentials in cassandra_config.py are "
              "correct before using this section.")
        return

    while True:
        print("\n--- Cassandra ---")
        print("1. Load data into Cassandra")
        print("2. CRUD operations")
        print("3. Feature: Commit activity by repo")
        print("4. Feature: Repository distribution by watch tier")
        print("5. Feature: License popularity")
        print("6. Back to main menu")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_cassandra_data("data")
        elif choice == "2":
            run_cassandra_crud()
        elif choice == "3":
            session = cassandra_config.get_session()
            repos = list_cassandra_repos(session)
            print("Available repos:", ", ".join(repos) if repos
                  else "none loaded yet")
            if repos:
                repo_choice = input("Enter a repo name from the list "
                                    "above: ").strip()
                show_cassandra_activity(repo_choice)
        elif choice == "4":
            print_cassandra_watch_report()
        elif choice == "5":
            print_cassandra_license_report()
        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


def mongo_menu():
    """MongoDB section of the application, added in part 2."""
    if not mongo_config.check_connection():
        print("\nCould not connect to MongoDB. Make sure the server is "
              "running before using this section.")
        return

    while True:
        print("\n--- MongoDB ---")
        print("1. Load data into MongoDB")
        print("2. CRUD operations")
        print("3. Feature: Common words in commit messages")
        print("4. Feature: Repository distribution by watch count")
        print("5. Feature: Repository name analysis")
        print("6. Back to main menu")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_mongo_data("data")
        elif choice == "2":
            run_mongo_crud()
        elif choice == "3":
            print_word_report()
        elif choice == "4":
            print_watch_report()
        elif choice == "5":
            print_name_report()
        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


def redis_menu():
    """Redis section of the application, built in part 1."""
    while True:
        print("\n--- Redis ---")
        print("1. Load data into Redis")
        print("2. CRUD operations")
        print("3. Feature: Language popularity")
        print("4. Feature: Commit activity by repo")
        print("5. Feature: License popularity")
        print("6. Back to main menu")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_redis_data("data")
        elif choice == "2":
            run_redis_crud()
        elif choice == "3":
            print_language_report()
        elif choice == "4":
            repos = list_available_repos()
            print("Available repos:", ", ".join(repos) if repos
                  else "none loaded yet")
            if repos:
                repo_choice = input("Enter a repo name from the list "
                                    "above: ").strip()
                show_commit_activity(repo_choice)
        elif choice == "5":
            print_license_report()
        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


def main():
    print("=== GitHub Archive Database Application ===")

    while True:
        print("\nSelect a database:")
        print("1. SQLite")
        print("2. Neo4j")
        print("3. Cassandra")
        print("4. MongoDB")
        print("5. Redis")
        print("6. Quit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            sqlite_menu()
        elif choice == "2":
            neo4j_menu()
        elif choice == "3":
            cassandra_menu()
        elif choice == "4":
            mongo_menu()
        elif choice == "5":
            redis_menu()
        elif choice == "6":
            # Close the Cassandra and Neo4j connections if either was
            # opened. Both drivers run background threads that keep the
            # process alive otherwise.
            cassandra_config.shutdown()
            neo4j_config.shutdown()
            print("Goodbye.")
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    main()
