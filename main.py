"""
main.py
OWNER: Person 4 (integration)

Purpose: This is the single entry point for the application. It ties
together data loading, CRUD operations, and both features into one
menu-driven program, which is what gets demonstrated in the video and
graded as "the application."

Do not write feature logic here. This file should only import and
call functions from the other four modules. If a menu option isn't
working, the bug almost always belongs in the module that owns it.

TODO:
    - Once data_loader.py, crud_operations.py, and both feature files
      are working on their own, wire them together below.
    - Test the full menu flow end to end before recording the video.
"""

from data_loader import load_all_data
from crud_operations import run_crud_menu
from feature_language_stats import print_language_report
from feature_commit_viz import show_commit_history


def main():
    print("=== GitHub Archive Redis Application ===")

    while True:
        print("\n1. Load data into Redis")
        print("2. CRUD operations")
        print("3. Feature: Language/technology popularity")
        print("4. Feature: Commit history visualization")
        print("5. Quit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            load_all_data("data")
        elif choice == "2":
            run_crud_menu()
        elif choice == "3":
            print_language_report()
        elif choice == "4":
            show_commit_history()
        elif choice == "5":
            print("Goodbye.")
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    main()
