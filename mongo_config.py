"""
mongo_config.py

Shared MongoDB connection setup used by every other MongoDB module in
this project. This is the MongoDB counterpart to redis_config.py from
part 1 of the project.

Nothing else in the project should create its own MongoClient. Keeping
the connection details in one file means the whole application can be
pointed at a different server by editing a single line here.
"""

from pymongo import MongoClient

# Update these values if your MongoDB instance runs somewhere other than
# localhost, or if it requires authentication.
MONGO_HOST = "localhost"
MONGO_PORT = 27017
DATABASE_NAME = "github_archive"

# Collection names, referenced by every other module so a rename only
# has to happen in one place.
COMMITS_COLLECTION = "commits"
REPOS_COLLECTION = "repos"
LICENSES_COLLECTION = "licenses"


def get_database():
    """
    Returns the MongoDB database object the rest of the application
    uses. Collections are accessed off of this, for example
    db[COMMITS_COLLECTION].
    """
    client = MongoClient(MONGO_HOST, MONGO_PORT)
    return client[DATABASE_NAME]


def check_connection():
    """
    Confirms the MongoDB server is reachable. Returns True on success,
    False if the connection fails, so the menu can show a useful
    message instead of raising a traceback at the user.
    """
    try:
        client = MongoClient(MONGO_HOST, MONGO_PORT,
                             serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Run this file directly to confirm MongoDB is reachable before
    # loading any data.
    if check_connection():
        print("Connected to MongoDB successfully.")
    else:
        print("Could not connect to MongoDB. Is the server running?")
