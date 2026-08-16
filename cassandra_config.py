"""
cassandra_config.py

Shared Cassandra connection setup and schema definition. This is the
Cassandra counterpart to redis_config.py from part 1 and
mongo_config.py from part 2.

Nothing else in the project should build its own Cluster object. Keeping
the contact points, credentials, and keyspace in one file means the
whole application can be pointed at a different node by editing this
file alone.

A note on the schema below: Cassandra does not let you query on
whatever field you feel like at runtime. Every query has to be served
by a partition key, so the table layout is designed backwards from the
questions the application asks. That is why the same commit is written
into more than one table. Storage is cheap, cluster-wide scans are not.
"""

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Update these if your Cassandra node runs somewhere other than the
# local machine.
CASSANDRA_HOSTS = ["127.0.0.1"]
CASSANDRA_PORT = 9042
KEYSPACE = "github_archive"

# Authentication. The lab environment runs Cassandra with the
# PasswordAuthenticator enabled, so a role is required to connect. Set
# USE_AUTH to False if you are running a stock node with
# AllowAllAuthenticator.
USE_AUTH = True
CASSANDRA_USER = "addsmi1720"
CASSANDRA_PASSWORD = "cassPass"

# Single node development cluster, so SimpleStrategy with one replica.
# A real deployment would use NetworkTopologyStrategy with a replication
# factor per data center.
REPLICATION = "{'class': 'SimpleStrategy', 'replication_factor': 1}"

# Every table this project uses. Each one exists to answer a specific
# question, which is the standard way to model data in Cassandra.
SCHEMA_STATEMENTS = [

    # CRUD table. Partitioned on the commit hash, so a lookup by hash
    # goes straight to the node holding that row.
    """
    CREATE TABLE IF NOT EXISTS commits_by_hash (
        commit_hash text PRIMARY KEY,
        repo_name text,
        author_name text,
        author_email text,
        committer_name text,
        subject text,
        message text,
        tree text,
        files_changed list<text>,
        num_files_changed int
    );
    """,

    # Same commit data, partitioned by repository instead. This is the
    # denormalization Cassandra expects: the row is written twice so
    # that "show me the commits in this repo" is a single partition
    # read rather than a scan across the cluster.
    """
    CREATE TABLE IF NOT EXISTS commits_by_repo (
        repo_name text,
        commit_hash text,
        author_name text,
        subject text,
        num_files_changed int,
        PRIMARY KEY ((repo_name), commit_hash)
    );
    """,

    # Counter table. Cassandra has no server-side GROUP BY, so counts
    # are maintained at write time instead of computed at read time.
    """
    CREATE TABLE IF NOT EXISTS commit_counts_by_author (
        repo_name text,
        author_name text,
        commit_count counter,
        PRIMARY KEY ((repo_name), author_name)
    );
    """,

    # Repositories bucketed into watch count tiers. The tier is the
    # partition key and watch_count is a clustering column ordered
    # descending, so the most watched repos in a tier come back already
    # sorted by the storage engine with no sorting done in Python.
    """
    CREATE TABLE IF NOT EXISTS repos_by_watch_tier (
        watch_tier text,
        watch_count int,
        repo_name text,
        PRIMARY KEY ((watch_tier), watch_count, repo_name)
    ) WITH CLUSTERING ORDER BY (watch_count DESC, repo_name ASC);
    """,

    # Histogram counts per tier, maintained during load for the same
    # reason as the author counters.
    """
    CREATE TABLE IF NOT EXISTS repo_counts_by_tier (
        bucket text,
        watch_tier text,
        repo_count counter,
        PRIMARY KEY ((bucket), watch_tier)
    );
    """,

    # License popularity counters. Everything lives under a single
    # partition key value because the list of distinct licenses is
    # small and the feature always reads all of them at once.
    """
    CREATE TABLE IF NOT EXISTS license_counts (
        bucket text,
        license_name text,
        repo_count counter,
        PRIMARY KEY ((bucket), license_name)
    );
    """,

    # The set of repositories that actually have commits loaded, so the
    # menu can show the user what they are allowed to pick.
    """
    CREATE TABLE IF NOT EXISTS repos_loaded (
        bucket text,
        repo_name text,
        PRIMARY KEY ((bucket), repo_name)
    );
    """,
]

# Partition key value used by the tables above that intentionally keep
# everything in one partition.
GLOBAL_BUCKET = "all"

# Module level session so repeated calls reuse one connection instead
# of opening a new cluster connection for every menu selection.
_session = None


def _build_cluster():
    """
    Builds the Cluster object, attaching credentials only when
    authentication is turned on.
    """
    auth_provider = None
    if USE_AUTH:
        auth_provider = PlainTextAuthProvider(
            username=CASSANDRA_USER, password=CASSANDRA_PASSWORD)

    return Cluster(CASSANDRA_HOSTS, port=CASSANDRA_PORT,
                   auth_provider=auth_provider)


def get_session():
    """
    Returns a session already pointed at the project keyspace, creating
    the keyspace and every table on first use. The session is cached so
    the rest of the application can call this freely.
    """
    global _session
    if _session is not None:
        return _session

    cluster = _build_cluster()
    session = cluster.connect()

    # The keyspace has to be created before it can be selected, and it
    # cannot be created from inside itself, so this runs on the bare
    # session first.
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {KEYSPACE} "
        f"WITH REPLICATION = {REPLICATION};")
    session.set_keyspace(KEYSPACE)

    for statement in SCHEMA_STATEMENTS:
        session.execute(statement)

    _session = session
    return _session


def check_connection():
    """
    Confirms the Cassandra node is reachable and the credentials work.
    Returns True on success and False on failure, so the menu can print
    a useful message instead of dropping a traceback on the user.
    """
    try:
        cluster = _build_cluster()
        session = cluster.connect()
        session.execute("SELECT release_version FROM system.local;")
        session.shutdown()
        cluster.shutdown()
        return True
    except Exception as error:
        print(f"  Cassandra connection error: {error}")
        return False


def shutdown():
    """
    Closes the cached session. Called on exit so the driver's
    background threads do not keep the process alive.
    """
    global _session
    if _session is not None:
        _session.cluster.shutdown()
        _session = None


if __name__ == "__main__":
    # Run this file directly to confirm Cassandra is reachable and the
    # schema builds cleanly before loading any data.
    if check_connection():
        get_session()
        print(f"Connected to Cassandra and created keyspace '{KEYSPACE}'.")
        shutdown()
    else:
        print("Could not connect to Cassandra. Is the node running?")
