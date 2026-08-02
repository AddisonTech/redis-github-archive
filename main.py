"""
main.py

Entry point for the GitHub Archive Redis application. Ties together
data loading, CRUD operations, and the three features into one
menu-driven program.
"""

from data_loader import load_all_data
from crud_operations import run_crud_menu
from feature_language_stats import print_language_report
from feature_license_stats import print_license_report
from feature_commit_activity import show_commit_activity, list_available_repos


def main():
    print("=== GitHub Archive Redis Application ===")

    while True:
        print("\n1. Load data into Redis")
        print("2. CRUD operations")
        print("3. Feature: Language popularity")
        print("4. Feature: Commit activity by repo")
        print("5. Feature: License popularity")
        print("6. Quit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_all_data("data")
        elif choice == "2":
            run_crud_menu()
        elif choice == "3":
            print_language_report()
        elif choice == "4":
            repos = list_available_repos()
            print("Available repos:", ", ".join(repos) if repos else "none loaded yet")
            if repos:
                repo_choice = input("Enter a repo name from the list above: ").strip()
                show_commit_activity(repo_choice)
        elif choice == "5":
            print_license_report()
        elif choice == "6":
            print("Goodbye.")
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    main()
