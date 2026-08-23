"""
neo4j_config.py

Shared Neo4j connection setup and schema constraints. This is the Neo4j
counterpart to redis_config.py (part 1), mongo_config.py (part 2), and
cassandra_config.py (part 3).

Nothing else in the project should build its own driver. Keeping the URI
and credentials here means the whole application can be pointed at a
different server by editing one file.

A note on what "schema" means in a graph database: Neo4j does not
require you to declare node labels or properties before writing them,
which is closer to MongoDB than to Cassandra. What it does support is
constraints and indexes, and those matter enormously here for a reason
that is not obvious. The loader uses MERGE, which is a find-or-create
operation. Without a uniqueness constraint backing the property being
merged on, every MERGE scans every node carrying that label. On a few
hundred thousand commits that turns a load into an overnight job. With
the constraint in place the same MERGE is an index lookup. The
constraints below are therefore created before any data is written,
not after.
"""

from neo4j import GraphDatabase

# Update these if your Neo4j server runs somewhere other than the local
# machine. Neo4j uses the Bolt protocol on 7687 by default; the browser
# interface on 7474 is not what the driver connects to.
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4jPass"

# The database to use. Neo4j Community Edition supports a single
# database named "neo4j"; Enterprise allows more.
NEO4J_DATABASE = "neo4j"

# Uniqueness constraints. Each one implicitly creates a backing index,
# which is what makes MERGE fast during loading.
CONSTRAINTS = [
    "CREATE CONSTRAINT commit_hash IF NOT EXISTS "
    "FOR (c:Commit) REQUIRE c.hash IS UNIQUE",

    "CREATE CONSTRAINT repo_name IF NOT EXISTS "
    "FOR (r:Repo) REQUIRE r.name IS UNIQUE",

    "CREATE CONSTRAINT author_name IF NOT EXISTS "
    "FOR (a:Author) REQUIRE a.name IS UNIQUE",

    "CREATE CONSTRAINT license_name IF NOT EXISTS "
    "FOR (l:License) REQUIRE l.name IS UNIQUE",

    "CREATE CONSTRAINT file_path IF NOT EXISTS "
    "FOR (f:File) REQUIRE f.path IS UNIQUE",
]

# Plain indexes on properties that are filtered or sorted but not unique.
INDEXES = [
    "CREATE INDEX repo_watch_count IF NOT EXISTS "
    "FOR (r:Repo) ON (r.watch_count)",
]

# Module level driver so repeated calls reuse one connection pool
# instead of opening a new one for every menu selection.
_driver = None


def get_driver():
    """
    Returns the shared driver, creating it and applying the constraints
    on first use. The driver is thread safe and holds a connection pool,
    so one instance for the life of the process is the intended usage.
    """
    global _driver
    if _driver is not None:
        return _driver

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        for statement in CONSTRAINTS + INDEXES:
            session.run(statement)

    _driver = driver
    return _driver


def get_session():
    """
    Returns a new session on the project database. Sessions are cheap
    and are not thread safe, so callers open one per unit of work rather
    than sharing a long lived one.

    Intended to be used as a context manager:

        with get_session() as session:
            session.run(...)
    """
    return get_driver().session(database=NEO4J_DATABASE)


def check_connection():
    """
    Confirms the Neo4j server is reachable and the credentials work.
    Returns True on success and False on failure, so the menu can print
    a useful message instead of dropping a traceback on the user.
    """
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception as error:
        print(f"  Neo4j connection error: {error}")
        return False


def shutdown():
    """
    Closes the driver and its connection pool. Called on exit so the
    driver's background threads do not keep the process alive.
    """
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


if __name__ == "__main__":
    # Run this file directly to confirm Neo4j is reachable and the
    # constraints apply cleanly before loading any data.
    if check_connection():
        get_driver()
        print(f"Connected to Neo4j at {NEO4J_URI} and applied constraints.")
        shutdown()
    else:
        print("Could not connect to Neo4j. Is the server running?")
