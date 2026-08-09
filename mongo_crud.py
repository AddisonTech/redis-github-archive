"""
mongo_crud.py

CRUD operations on commit documents stored in MongoDB. This is the
MongoDB counterpart to crud_operations.py from part 1 of the project.

The commit hash is the document _id, so every operation here is a
primary key lookup. Note the difference from the Redis version: because
MongoDB stores the whole document together, deleting a commit is a
single operation. The Redis version had to also remove the hash from
its repo set and decrement its author sorted set to avoid leaving
orphaned index entries behind.
"""

from mongo_config import get_database, COMMITS_COLLECTION


def create_record(db, commit_hash, repo_name, author_name, subject, message=""):
    """
    Inserts a new commit document. Returns False if a document with
    that commit hash already exists, since _id must be unique.
    """
    collection = db[COMMITS_COLLECTION]
    if collection.find_one({"_id": commit_hash}):
        return False

    collection.insert_one({
        "_id": commit_hash,
        "repo_name": repo_name,
        "author_name": author_name,
        "author_email": "",
        "committer_name": author_name,
        "subject": subject,
        "message": message,
        "tree": "",
        "files_changed": [],
        "num_files_changed": 0,
    })
    return True


def read_record(db, commit_hash):
    """
    Returns one commit document by its hash, or None if not found.
    """
    return db[COMMITS_COLLECTION].find_one({"_id": commit_hash})


def update_record(db, commit_hash, fields):
    """
    Updates one or more fields on an existing commit document. fields
    is a dictionary, for example {"subject": "new subject"}. Returns
    False if no document matched.
    """
    result = db[COMMITS_COLLECTION].update_one(
        {"_id": commit_hash}, {"$set": fields})
    return result.matched_count > 0


def delete_record(db, commit_hash):
    """
    Deletes a commit document. Returns False if nothing was deleted.
    """
    result = db[COMMITS_COLLECTION].delete_one({"_id": commit_hash})
    return result.deleted_count > 0


def search_by_author(db, author_name, limit=10):
    """
    Finds commits by author name using a case-insensitive regular
    expression. This shows off a query capability the Redis version
    could not offer without building a dedicated index for it, since
    Redis has no equivalent of querying inside a value.
    """
    cursor = db[COMMITS_COLLECTION].find(
        {"author_name": {"$regex": author_name, "$options": "i"}}
    ).limit(limit)
    return list(cursor)


def run_crud_menu():
    """
    Text menu exercising all four CRUD operations plus author search
    against the commits collection.
    """
    db = get_database()

    while True:
        print("\n1. Create  2. Read  3. Update  4. Delete  "
              "5. Search by author  6. Back to Main Menu")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            commit_hash = input("New commit hash (any unique string): ").strip()
            repo_name = input("Repo name: ").strip()
            author_name = input("Author name: ").strip()
            subject = input("Commit subject: ").strip()
            if create_record(db, commit_hash, repo_name, author_name, subject):
                print("Commit created.")
            else:
                print("A commit with that hash already exists.")

        elif choice == "2":
            commit_hash = input("Commit hash to look up: ").strip()
            doc = read_record(db, commit_hash)
            if doc:
                for field, value in doc.items():
                    print(f"  {field}: {value}")
            else:
                print("No commit found with that hash.")

        elif choice == "3":
            commit_hash = input("Commit hash to update: ").strip()
            field = input("Field to update (e.g. subject): ").strip()
            value = input("New value: ").strip()
            if update_record(db, commit_hash, {field: value}):
                print("Commit updated.")
            else:
                print("No commit found with that hash.")

        elif choice == "4":
            commit_hash = input("Commit hash to delete: ").strip()
            if delete_record(db, commit_hash):
                print("Commit deleted.")
            else:
                print("No commit found with that hash.")

        elif choice == "5":
            author_name = input("Author name to search for: ").strip()
            results = search_by_author(db, author_name)
            if not results:
                print("No commits found for that author.")
            else:
                print(f"\nFound {len(results)} commit(s):")
                for doc in results:
                    print(f"  [{doc['_id'][:10]}] {doc['repo_name']}: "
                          f"{doc.get('subject', '')[:60]}")

        elif choice == "6":
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    run_crud_menu()
