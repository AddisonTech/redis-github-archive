"""
data_loader.py
OWNER: Person 1

Purpose: Read the JSON files from the GitHubArchive dataset and load them
into Redis using a schema you design. Everyone else's code (CRUD and both
features) depends on the keys and structures you decide on here, so agree
on the schema with Person 2 early and document it clearly at the top of
this file once it's finalized.

Suggested schema (edit this once you settle on your real one):
    event:<event_id>          -> Redis Hash of one GitHub event's fields
    events:by_type:<type>     -> Redis Set of event_ids for that event type
    events:by_actor:<login>   -> Redis Set of event_ids by that user

TODO:
    - Unzip / locate the GitHubArchive-Dataset files
    - Parse each JSON record
    - Decide final key structure and update the docstring above
    - Load records into Redis using the connection from redis_config.py
"""

import json
import os
from redis_config import get_redis_connection


def load_json_files(data_dir):
    """
    Reads every .json file in data_dir and returns a list of parsed
    Python dictionaries, one per GitHub event.

    TODO: implement file reading and json.loads() parsing here.
    """
    records = []
    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                # TODO: some GitHub Archive files are one JSON object
                # per line rather than a single JSON array. Confirm the
                # dataset's actual format before finishing this loop.
                pass
    return records


def store_event(r, event):
    """
    Takes one parsed event dictionary and stores it in Redis according
    to the schema documented above.

    TODO: implement using r.hset() for the event hash and r.sadd() for
    the index sets (by type, by actor, etc).
    """
    pass


def load_all_data(data_dir):
    """
    Main entry point for this module. Connects to Redis, loads all JSON
    files from data_dir, and stores each event.

    This is the function main.py will call, so keep the name and
    signature stable once the rest of the team is depending on it.
    """
    r = get_redis_connection()
    records = load_json_files(data_dir)
    for event in records:
        store_event(r, event)
    print(f"Loaded {len(records)} events into Redis.")


if __name__ == "__main__":
    # Lets Person 1 test this file on its own without running main.py
    load_all_data("data")
