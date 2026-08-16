"""
main.py

Entry point for the GitHub Archive database application.

The project now supports three NoSQL databases, one per part of the
course project:

    Part 1  Redis      key-value store
    Part 2  MongoDB    document store
    Part 3  Cassandra  column-family store

All three implementations are kept in the same project rather than
replaced, so the same application can be run against each one and the
differences between the three data models can be compared directly.
That comparison is the point of building the application three times.

Run with: python main.py
"""

import cassandra_config
import mongo_config

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
        print("1. Cassandra")
        print("2. MongoDB")
        print("3. Redis")
        print("4. Quit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            cassandra_menu()
        elif choice == "2":
            mongo_menu()
        elif choice == "3":
            redis_menu()
        elif choice == "4":
            # Close the Cassandra session if one was opened. The driver
            # runs background threads that keep the process alive
            # otherwise.
            cassandra_config.shutdown()
            print("Goodbye.")
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    main()
