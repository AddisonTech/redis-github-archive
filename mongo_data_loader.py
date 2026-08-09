"""
mongo_data_loader.py

Loads the GitHub Archive dataset into MongoDB collections. This is the
MongoDB counterpart to data_loader.py from part 1 of the project.

Where the Redis version had to flatten each record into hashes and
maintain separate index structures by hand, MongoDB stores each JSON
record as a document more or less as-is. Nested fields such as the
author object and the difference array survive intact, which means the
aggregation features can reach into them directly instead of relying on
indexes built during loading.

Collections created:
    commits   from Sample_Commits.json, one document per commit
    repos     from Sample_Repos.json, one document per repo with watch_count
    licenses  from Licenses.json, one document per repo with its license

Indexes are created after loading to keep the CRUD lookups and the
aggregation features fast.
"""

import json
import os
from pymongo import ASCENDING, DESCENDING
from mongo_config import (get_database, COMMITS_COLLECTION,
                          REPOS_COLLECTION, LICENSES_COLLECTION)

BATCH_SIZE = 5000


def _insert_in_batches(collection, filepath, transform, label):
    """
    Streams a newline-delimited JSON file and inserts documents in
    batches with insert_many. Batching matters here because inserting
    one document at a time across hundreds of thousands of records
    means a round trip to the server for every single one.

    transform is a function that takes the parsed record and returns
    the document to insert, or None to skip that record.
    """
    batch = []
    count = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            doc = transform(record)
            if doc is None:
                continue

            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                collection.insert_many(batch)
                count += len(batch)
                batch = []
                print(f"  ...{count:,} {label} inserted")

    if batch:
        collection.insert_many(batch)
        count += len(batch)

    print(f"Loaded {count:,} {label}.")
    return count


def load_commits(db, filepath):
    """
    Loads Sample_Commits.json into the commits collection. The commit
    hash is used as the document _id, which gives a unique primary key
    for free and makes CRUD lookups by hash an indexed operation.
    """
    collection = db[COMMITS_COLLECTION]
    collection.drop()

    def transform(record):
        commit_hash = record.get("commit")
        repo_name = record.get("repo_name")
        if not commit_hash or not repo_name:
            return None

        author = record.get("author") or {}
        committer = record.get("committer") or {}
        difference = record.get("difference") or []

        return {
            "_id": commit_hash,
            "repo_name": repo_name,
            "author_name": author.get("name", "unknown"),
            "author_email": author.get("email", ""),
            "committer_name": committer.get("name", "unknown"),
            "subject": record.get("subject", ""),
            "message": record.get("message", ""),
            "tree": record.get("tree", ""),
            "files_changed": [d.get("new_path") for d in difference
                              if d.get("new_path")],
            "num_files_changed": len(difference),
        }

    count = _insert_in_batches(collection, filepath, transform, "commits")

    print("  creating indexes on commits...")
    collection.create_index([("repo_name", ASCENDING)])
    collection.create_index([("author_name", ASCENDING)])
    return count


def load_repos(db, filepath):
    """
    Loads Sample_Repos.json into the repos collection. watch_count
    arrives as a string in the source data and is converted to an
    integer here, since the watch distribution feature needs to do
    numeric bucketing on it.
    """
    collection = db[REPOS_COLLECTION]
    collection.drop()

    def transform(record):
        repo_name = record.get("repo_name")
        if not repo_name:
            return None
        try:
            watch_count = int(record.get("watch_count", 0))
        except (TypeError, ValueError):
            watch_count = 0
        return {
            "repo_name": repo_name,
            "watch_count": watch_count,
            "name_length": len(repo_name),
        }

    count = _insert_in_batches(collection, filepath, transform, "repos")

    print("  creating indexes on repos...")
    collection.create_index([("watch_count", DESCENDING)])
    collection.create_index([("name_length", ASCENDING)])
    return count


def load_licenses(db, filepath):
    """
    Loads Licenses.json into the licenses collection, one document per
    repository.
    """
    collection = db[LICENSES_COLLECTION]
    collection.drop()

    def transform(record):
        repo_name = record.get("repo_name")
        license_name = record.get("license")
        if not repo_name or not license_name:
            return None
        return {"repo_name": repo_name, "license": license_name}

    count = _insert_in_batches(collection, filepath, transform, "licenses")

    print("  creating index on licenses...")
    collection.create_index([("license", ASCENDING)])
    return count


def load_all_data(data_dir="data"):
    """
    Main entry point called from main.py. Drops and reloads all three
    collections so the load is repeatable, then builds the indexes.
    """
    db = get_database()

    print("Loading commits...")
    load_commits(db, os.path.join(data_dir, "Sample_Commits.json"))

    print("Loading repos...")
    load_repos(db, os.path.join(data_dir, "Sample_Repos.json"))

    print("Loading licenses...")
    load_licenses(db, os.path.join(data_dir, "Licenses.json"))

    print("All data loaded into MongoDB.")


if __name__ == "__main__":
    load_all_data("data")
