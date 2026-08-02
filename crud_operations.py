"""
crud_operations.py

CRUD operations on commit records stored in Redis by data_loader.py.
Each commit is identified by its Git commit hash.
"""

import json
from redis_config import get_redis_connection


def create_record(r, commit_hash, repo_name, author_name, subject, message=""):
    """
    Adds a new commit record to Redis, indexed the same way
    data_loader.py indexes loaded commits so it behaves consistently
    with the rest of the data.
    """
    key = f"commit:{commit_hash}"
    r.hset(key, mapping={
        "repo_name": repo_name,
        "author_name": author_name,
        "author_email": "",
        "committer_name": author_name,
        "subject": subject,
        "message": message,
        "tree": "",
        "files_changed": json.dumps([]),
        "num_files_changed": 0,
    })
    r.sadd(f"commits:by_repo:{repo_name}", commit_hash)
    r.zincrby(f"commits:by_author:{repo_name}", 1, author_name)
    r.sadd("repos:loaded", repo_name)
    return key


def read_record(r, commit_hash):
    """
    Retrieves one commit record. Returns None if it doesn't exist.
    """
    key = f"commit:{commit_hash}"
    if not r.exists(key):
        return None
    return r.hgetall(key)


def update_record(r, commit_hash, fields):
    """
    Updates one or more fields on an existing commit record. fields is
    a dictionary, for example {"subject": "new subject"}. Returns False
    if the record doesn't exist.
    """
    key = f"commit:{commit_hash}"
    if not r.exists(key):
        return False
    r.hset(key, mapping=fields)
    return True


def delete_record(r, commit_hash):
    """
    Removes a commit record and cleans it out of the repo and author
    indexes it was added to. Returns False if it didn't exist.
    """
    key = f"commit:{commit_hash}"
    record = r.hgetall(key)
    if not record:
        return False

    repo_name = record.get("repo_name")
    author_name = record.get("author_name")

    r.delete(key)
    if repo_name:
        r.srem(f"commits:by_repo:{repo_name}", commit_hash)
        if author_name:
            r.zincrby(f"commits:by_author:{repo_name}", -1, author_name)
    return True


def run_crud_menu():
    """
    Text menu that exercises all four CRUD operations against the
    commit data in Redis.
    """
    r = get_redis_connection()

    while True:
        print("\n1. Create  2. Read  3. Update  4. Delete  5. Back to Main Menu")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            commit_hash = input("New commit hash (any unique string): ").strip()
            repo_name = input("Repo name: ").strip()
            author_name = input("Author name: ").strip()
            subject = input("Commit subject: ").strip()
            create_record(r, commit_hash, repo_name, author_name, subject)
            print("Commit created.")

        elif choice == "2":
            commit_hash = input("Commit hash to look up: ").strip()
            record = read_record(r, commit_hash)
            if record:
                for field, value in record.items():
                    print(f"  {field}: {value}")
            else:
                print("No commit found with that hash.")

        elif choice == "3":
            commit_hash = input("Commit hash to update: ").strip()
            field = input("Field to update (e.g. subject): ").strip()
            value = input("New value: ").strip()
            if update_record(r, commit_hash, {field: value}):
                print("Commit updated.")
            else:
                print("No commit found with that hash.")

        elif choice == "4":
            commit_hash = input("Commit hash to delete: ").strip()
            if delete_record(r, commit_hash):
                print("Commit deleted.")
            else:
                print("No commit found with that hash.")

        elif choice == "5":
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    run_crud_menu()
