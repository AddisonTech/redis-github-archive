"""
data_loader.py

Loads the real dataset files into Redis. This project uses three of the
provided files:

    Sample_Commits.json  -> the main commit records (this is the CRUD entity)
    Languages.json         -> aggregated into a language popularity leaderboard
    Licenses.json          -> aggregated into a license popularity leaderboard

Files.json and Contents.json are not loaded. Their repo names barely overlap
with the commit data (each file is an independent random sample from the
course dataset), and Contents.json alone is hundreds of megabytes of raw
file text that none of the three features below actually need. You're
welcome to extend the project to use them later for extra credit or a
future part of the project.

Redis schema used by this project:
    commit:<commit_hash>              Hash       full commit record
    commits:by_repo:<repo_name>       Set        commit hashes for that repo
    commits:by_author:<repo_name>     Sorted Set author name -> commit count
    repos:loaded                      Set        every repo_name with commits loaded

    languages:ranked                  Sorted Set language name -> total bytes
    licenses:ranked                   Sorted Set license name -> repo count
"""

import json
import os
from redis_config import get_redis_connection

PIPELINE_BATCH_SIZE = 2000


def load_commits(r, filepath):
    """
    Loads Sample_Commits.json into Redis. Each commit becomes a hash,
    indexed by repo (for lookups) and by author (for the commit activity
    feature).
    """
    pipe = r.pipeline()
    ops_since_execute = 0
    count = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                commit = json.loads(line)
            except json.JSONDecodeError:
                continue

            commit_hash = commit.get("commit")
            repo_name = commit.get("repo_name")
            if not commit_hash or not repo_name:
                continue

            author = commit.get("author") or {}
            committer = commit.get("committer") or {}
            difference = commit.get("difference") or []
            author_name = author.get("name", "unknown")

            key = f"commit:{commit_hash}"
            pipe.hset(key, mapping={
                "repo_name": repo_name,
                "author_name": author_name,
                "author_email": author.get("email", ""),
                "committer_name": committer.get("name", "unknown"),
                "subject": commit.get("subject", ""),
                "message": commit.get("message", ""),
                "tree": commit.get("tree", ""),
                "files_changed": json.dumps(
                    [d.get("new_path") for d in difference if d.get("new_path")]
                ),
                "num_files_changed": len(difference),
            })
            pipe.sadd(f"commits:by_repo:{repo_name}", commit_hash)
            pipe.zincrby(f"commits:by_author:{repo_name}", 1, author_name)
            pipe.sadd("repos:loaded", repo_name)

            count += 1
            ops_since_execute += 4
            if ops_since_execute >= PIPELINE_BATCH_SIZE:
                pipe.execute()
                pipe = r.pipeline()
                ops_since_execute = 0
                print(f"  ...{count} commits loaded")

    pipe.execute()
    print(f"Loaded {count} commits.")


def load_languages(r, filepath):
    """
    Streams Languages.json (a few million lines covering the full
    dataset) and aggregates total bytes per language into one sorted
    set. Only the aggregate is stored, not one entry per repo, since
    storing every repo's language breakdown individually would create
    millions of keys that the language popularity feature doesn't need.
    """
    pipe = r.pipeline()
    ops_since_execute = 0
    line_count = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            for lang in record.get("language") or []:
                name = lang.get("name")
                try:
                    byte_count = int(lang.get("bytes", 0))
                except (TypeError, ValueError):
                    byte_count = 0
                if name:
                    pipe.zincrby("languages:ranked", byte_count, name)
                    ops_since_execute += 1

            if ops_since_execute >= PIPELINE_BATCH_SIZE:
                pipe.execute()
                pipe = r.pipeline()
                ops_since_execute = 0

            if line_count % 500000 == 0:
                print(f"  ...{line_count:,} language records scanned")

    pipe.execute()
    print(f"Finished scanning {line_count:,} language records.")


def load_licenses(r, filepath):
    """
    Loads Licenses.json and aggregates how many repos use each license
    into a sorted set, the same pattern used for languages above.
    """
    pipe = r.pipeline()
    ops_since_execute = 0
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

            license_name = record.get("license")
            if license_name:
                pipe.zincrby("licenses:ranked", 1, license_name)
                count += 1
                ops_since_execute += 1

            if ops_since_execute >= PIPELINE_BATCH_SIZE:
                pipe.execute()
                pipe = r.pipeline()
                ops_since_execute = 0

    pipe.execute()
    print(f"Loaded license data for {count} repos.")


def load_all_data(data_dir="data"):
    """
    Main entry point called from main.py. Loads all three data sources
    into Redis. Languages.json is by far the largest file, so that step
    takes the longest; the progress prints let you know it's still
    working rather than stuck.
    """
    r = get_redis_connection()

    print("Loading commits...")
    load_commits(r, os.path.join(data_dir, "Sample_Commits.json"))

    print("Loading licenses...")
    load_licenses(r, os.path.join(data_dir, "Licenses.json"))

    print("Loading languages (largest file, this step takes the longest)...")
    load_languages(r, os.path.join(data_dir, "Languages.json"))

    print("All data loaded.")


if __name__ == "__main__":
    load_all_data("data")
