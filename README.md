# GitHub Archive Database Integration

A Python application that loads real GitHub Archive data into a database
and performs CRUD operations and analysis on it.

The project is built in parts, one database per part:

| Part | Database | Type |
|------|----------|------|
| 1 | **Redis** | Key-value store |
| 2 | **MongoDB** | Document store |
| 3 | **Cassandra** | Column-family store |
| 4 | **Neo4j** | Graph store |
| 5 | **SQLite** | Relational store |

All five implementations live in the same project so the same
application can be run against each one and the five data models
compared side by side. The first four are NoSQL; the fifth is
relational, which is what makes the comparison worth making.

## Dependencies
- Python 3.10 or later
- SQLite (no installation needed, `sqlite3` ships with Python)
- Neo4j server (for the Neo4j section)
- Cassandra node (for the Cassandra section)
- MongoDB server (for the MongoDB section)
- Redis server (for the Redis section)
- neo4j (`pip install neo4j`)
- cassandra-driver (`pip install cassandra-driver`)
- pymongo (`pip install pymongo`)
- redis-py (`pip install redis`)
- matplotlib (`pip install matplotlib`), used by the commit activity
  features to render a bar chart of top contributors

Install everything at once with:
```
pip install -r requirements.txt
```

## Technology Requirements
- No server required for the SQLite section. The database is a single
  file, `github_archive.db`, created in the project root on first use.
- A running Neo4j server on bolt://localhost:7687
- A running Cassandra node on 127.0.0.1:9042
- A running MongoDB instance on localhost:27017
- A running Redis instance on localhost:6379
- Dataset files placed in a `data/` folder in the project root:
  `Sample_Commits.json`, `Sample_Repos.json`, `Licenses.json`,
  `Languages.json`

The dataset files are not committed to this repository. They are
several hundred megabytes combined, which exceeds GitHub's file size
limits. The `data/` folder is listed in `.gitignore`.

## Setup
1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Start Neo4j, Cassandra, MongoDB, and/or Redis depending on which
   section you plan to use. The SQLite section needs nothing started.
4. If Cassandra is running with the `PasswordAuthenticator` enabled,
   set the role name and password in `cassandra_config.py`. If it is
   running with `AllowAllAuthenticator`, set `USE_AUTH = False` there
   instead.
5. Set the Neo4j username and password in `neo4j_config.py`. Neo4j
   requires a password change on first login, so the value there must
   match whatever the server was set to.
6. Create a `data/` folder in the project root and place the dataset
   files inside it.
7. Run the application: `python main.py`
8. Choose a database, then choose option 1 to load data before using
   CRUD or any feature. Every other option reads from what the load
   step creates.

The Cassandra keyspace and tables are created automatically on first
connection, so no manual `cqlsh` setup is required. The Neo4j
constraints and indexes are likewise applied automatically before any
data is written.

## Project Structure
```
redis-github-archive/
├── main.py                                # Entry point, database selection menu
│
├── sqlite_config.py                       # SQLite connection and schema
├── sqlite_data_loader.py                  # Loads dataset into SQLite tables
├── sqlite_crud.py                         # CRUD on commit rows
├── feature_sqlite_file_activity.py        # SQLite feature 1
├── feature_sqlite_committers.py           # SQLite feature 2
├── feature_sqlite_contributor_ranking.py  # SQLite feature 3
│
├── neo4j_config.py                        # Neo4j connection and constraints
├── neo4j_data_loader.py                   # Loads dataset into the graph
├── neo4j_crud.py                          # CRUD on commit nodes
├── feature_neo4j_collaboration.py         # Neo4j feature 1
├── feature_neo4j_repo_similarity.py       # Neo4j feature 2
├── feature_neo4j_degrees_of_separation.py # Neo4j feature 3
│
├── cassandra_config.py                    # Cassandra connection, keyspace, schema
├── cassandra_data_loader.py               # Loads dataset into Cassandra tables
├── cassandra_crud.py                      # CRUD on commit rows
├── feature_cassandra_commit_activity.py   # Cassandra feature 1
├── feature_cassandra_watch_tiers.py       # Cassandra feature 2
├── feature_cassandra_licenses.py          # Cassandra feature 3
│
├── mongo_config.py                        # MongoDB connection settings
├── mongo_data_loader.py                   # Loads dataset into MongoDB collections
├── mongo_crud.py                          # CRUD on commit documents
├── feature_commit_words.py                # MongoDB feature 1
├── feature_watch_distribution.py          # MongoDB feature 2
├── feature_repo_names.py                  # MongoDB feature 3
│
├── redis_config.py                        # Redis connection settings
├── data_loader.py                         # Loads dataset into Redis
├── crud_operations.py                     # CRUD on commit records
├── feature_language_stats.py              # Redis feature 1
├── feature_commit_activity.py             # Redis feature 2
├── feature_license_stats.py               # Redis feature 3
│
├── secureCassandra.py                     # Standalone SASL authentication demo
└── requirements.txt
```

## SQLite Section (Part 5)

SQLite is the only relational database in this project and the only one
of the five that needs no server. There is no host, no port, and no
credentials, because the database is a single file and the library runs
inside the application process.

### Schema
```
licenses      license_id PK, name UNIQUE
authors       author_id PK, name UNIQUE, email
repos         repo_id PK, repo_name UNIQUE, watch_count,
              license_id FK -> licenses ON DELETE SET NULL
commits       commit_hash PK, repo_id FK -> repos ON DELETE CASCADE,
              author_id FK -> authors ON DELETE CASCADE,
              subject, message, num_files_changed
commit_files  file_id PK, commit_hash FK -> commits ON DELETE CASCADE,
              file_path
```

This is a normalized schema: each fact is stored once and referenced by
foreign key everywhere else. Every earlier part had to denormalize in
some form. Redis hand-built parallel index structures, Cassandra wrote
the same commit into two tables, Neo4j derived a redundant relationship
to keep traversals cheap, and MongoDB embedded values a relational
schema would point at. None of that is needed here, because the join
happens at query time rather than being designed around in advance.

Note that SQLite ships with foreign key enforcement **off** by default
for backward compatibility. The `PRAGMA foreign_keys = ON` in
`sqlite_config.py` is what turns the declarations above into rules
rather than documentation, and it must be set per connection.

Indexes are created on every foreign key column and on `watch_count`.
SQLite indexes PRIMARY KEY and UNIQUE columns automatically but not
REFERENCES columns, and every feature joins on those.

### CRUD Operations
Create, Read, Update, and Delete on commit rows, keyed by hash, plus a
case-insensitive author search.

- **Create** runs in a transaction across three tables, since the author
  and repo rows must exist first. If the commit insert fails, the
  rollback removes the author and repo rows too. A real multi-table
  rollback is something none of the four NoSQL parts offered; the
  closest was Cassandra's logged batch, which guarantees eventual
  application but gives no isolation.
- **Read** joins commits, authors, repos, and licenses in one statement.
- **Update** validates the column against an allowlist, since column
  names cannot be parameterized, then uses `rowcount` to report whether
  the row existed without a separate read first.
- **Delete** relies on `ON DELETE CASCADE`. Removing a commit removes
  its file rows inside the database. Redis and Cassandra both required
  the application to do this by hand and would leave orphans if it
  forgot; Neo4j refused the delete until relationships were removed
  manually. SQLite is the only one of the five that quietly does the
  right thing.

Every query is parameterized with `?` placeholders.

### Features
1. **File activity in the most watched repositories.** A four-table join
   across `commit_files`, `commits`, `repos`, and `licenses`. Reports
   commits, distinct files touched, total file changes, and average
   files per commit per repository. `COUNT(DISTINCT file_path)` and
   `COUNT(file_id)` answer two different questions from one join: how
   much of the codebase was touched versus how much churn there was.
   A second query uses `HAVING` to find the most frequently changed
   individual files, filtering on the aggregate in a way `WHERE` cannot.
2. **Committers per repository.** Aggregates an aggregate: the average
   number of committers per repository is the mean of a count, which
   cannot be produced by a single `GROUP BY`. Common table expressions
   name the intermediate result so the outer query can average it. Also
   produces a distribution histogram with `CASE` and a commits-per-person
   ratio, and renders a matplotlib chart.
3. **Top contributors ranked within each repository.** Uses window
   functions. `ROW_NUMBER() OVER (PARTITION BY repo_id ORDER BY commits
   DESC)` ranks contributors inside each repository without collapsing
   the rows, so the top three for *every* repository come back in one
   query rather than one query per repository. `SUM(...) OVER
   (PARTITION BY ...)` puts each repository's total on every row, making
   the percentage share possible without a self join. A second report
   measures contribution concentration: what share of a repository's
   commits came from its single most active contributor.

### Loading
The load runs parents first, since a commit row carries foreign keys
that must already exist. `Sample_Commits.json` is read in two passes,
the first collecting distinct authors and repositories and the second
inserting the commits. Two passes is slower than one, but the
alternative is a lookup query per record, and reading the file twice is
cheaper than that.

Three things keep inserts fast. `executemany` inside a single
transaction per batch, because SQLite syncs to disk at the end of every
transaction and autocommit would mean one sync per row. Relaxed
`journal_mode` and `synchronous` PRAGMAs during the bulk load, restored
afterward, trading crash durability for speed on an operation that can
simply be re-run. And id lookups cached in Python dictionaries rather
than queried per row.

`ANALYZE` runs after loading. It collects statistics the query planner
uses to choose join order, and without it the planner guesses.

## Neo4j Section (Part 4)

### Graph Model
```
(:Author  {name, email})
(:Commit  {hash, subject, message, num_files_changed})
(:Repo    {name, watch_count})
(:File    {path})
(:License {name})

(Author)-[:AUTHORED]->(Commit)
(Commit)-[:IN_REPO]->(Repo)
(Commit)-[:MODIFIED]->(File)
(Repo)-[:LICENSED_UNDER]->(License)
(Author)-[:CONTRIBUTED_TO {commits: n}]->(Repo)
```

The first four relationships come from the source data. `CONTRIBUTED_TO`
is derived after loading by rolling up each author's commits per
repository into one weighted edge. It is technically redundant, since
the same information is reachable by walking Author to Commit to Repo,
but every feature in this section traverses author-to-repo constantly
and collapsing thousands of commit hops into one edge is what keeps
those traversals cheap. It is the graph equivalent of the Cassandra
section storing each commit in two tables.

Uniqueness constraints on `Commit.hash`, `Repo.name`, `Author.name`,
`License.name`, and `File.path` are applied **before** any data is
written. This is not cosmetic. The loader uses `MERGE`, and without a
constraint backing the merged property, every `MERGE` scans every node
carrying that label. With the constraint it is an index lookup.

Licenses are modeled as nodes rather than as a property on `Repo`, so
that finding every repository sharing a license is one hop off a single
node instead of a scan.

### CRUD Operations
Create, Read, Update, and Delete on commit nodes, keyed by hash, plus a
case-insensitive author search.

- **Create** uses `MERGE` to attach the commit to its author and repo,
  creating either if absent, and adjusts the `CONTRIBUTED_TO` weight.
  Existence is checked separately, because `MERGE` on an existing hash
  would silently match and overwrite rather than report a conflict.
- **Read** returns the commit with its author, repository, and modified
  files in one query. The joins are the traversal.
- **Update** validates the property name against an allowlist, since
  property names cannot be parameterized in Cypher, the same
  restriction CQL has on column names.
- **Delete** uses `DETACH DELETE`. Neo4j refuses to delete a node that
  still has relationships, so the database itself prevents the dangling
  references that Redis and Cassandra both permitted and left to the
  application to avoid.

### Features
1. **Collaboration patterns between authors.** Matches the shape
   `(a1)-[:CONTRIBUTED_TO]->(r)<-[:CONTRIBUTED_TO]-(a2)` to find authors
   who work on the same repositories, ranked by how many they share.
   The pattern is the entire logic; there is no join to construct.
   Can also list the closest collaborators for one named author.
2. **Repository similarity by shared contributors.** A two hop traversal
   out through a repository's contributors and back down into
   everything else they touched. Scored by the Jaccard index rather than
   raw overlap, so a large repository does not rank as similar to
   everything simply by being large.
3. **Degrees of separation between two authors.** Uses `shortestPath()`
   to find the shortest chain of shared repositories linking two
   contributors. This is the one query in the whole project that has no
   reasonable implementation in any of the other three databases, since
   the hop count is not known in advance and each hop depends on the
   last. The search runs over the existing bipartite author-to-repo
   structure rather than a materialized `COLLABORATED_WITH` edge, which
   would need n * (n - 1) / 2 relationships per repository and add
   millions of edges without making the graph any more expressive.

### Loading
Writes go out as `UNWIND` over a batch parameter, 2,000 rows per
statement, so a batch is one round trip and one query plan rather than
one of each per row. The graph is cleared with
`CALL { ... } IN TRANSACTIONS`, which commits in chunks, because
deleting several hundred thousand nodes in a single transaction is a
reliable way to exhaust the heap. Files per commit are capped, since a
handful of commits touch thousands of files and would otherwise
dominate the node count without changing any result.

## Cassandra Section (Part 3)

### Keyspace and Tables
Keyspace `github_archive`, created with `SimpleStrategy` and a
replication factor of 1 for single-node development.

```
commits_by_hash          PRIMARY KEY (commit_hash)
                         Full commit record. Serves every CRUD lookup.

commits_by_repo          PRIMARY KEY ((repo_name), commit_hash)
                         The same commits partitioned by repository, so
                         browsing a repo is one partition read.

commit_counts_by_author  PRIMARY KEY ((repo_name), author_name)
                         Counter column, incremented at write time.

repos_by_watch_tier      PRIMARY KEY ((watch_tier), watch_count, repo_name)
                         CLUSTERING ORDER BY (watch_count DESC, repo_name ASC)
                         Repos stored pre-sorted by watch count inside
                         each tier.

repo_counts_by_tier      PRIMARY KEY ((bucket), watch_tier)
                         Counter column for the distribution histogram.

license_counts           PRIMARY KEY ((bucket), license_name)
                         Counter column, one row per distinct license.

repos_loaded             PRIMARY KEY ((bucket), repo_name)
                         The repositories that have commit data loaded.
```

Every table above exists to answer one specific question. Cassandra
serves queries from partition keys, not from arbitrary predicates, so
the schema is designed backwards from the application's access patterns
rather than normalized around the data. That is why the same commit is
written to two tables during loading.

### CRUD Operations
Create, Read, Update, and Delete on individual commit rows, keyed by
commit hash, plus a per-repository commit listing.

- **Create** uses `IF NOT EXISTS`, a lightweight transaction, because a
  plain Cassandra `INSERT` is an upsert and would silently overwrite an
  existing commit.
- **Update** checks for existence first, since an `UPDATE` against a
  missing partition key creates the row rather than failing, and
  validates the column name against an allowlist before it reaches the
  statement.
- **Delete** removes the row from both commit tables in a logged batch
  and decrements the author counter separately, since counter and
  non-counter statements cannot share a batch.
- **List by repo** reads `commits_by_repo`, which is exactly why that
  second table exists. The same query against `commits_by_hash` would
  require `ALLOW FILTERING` and a cluster-wide scan.

### Features
1. **Commit activity by repository.** Top contributors read from the
   `commit_counts_by_author` counter table. Cassandra has no GROUP BY,
   so the counts are maintained during loading rather than computed at
   read time. Renders a matplotlib bar chart.
2. **Repository distribution by watch tier.** A histogram built from
   `repo_counts_by_tier`, plus the most watched repositories read from
   `repos_by_watch_tier`. The clustering order stores those rows
   already sorted by watch count, so the top N is a sequential read
   with `LIMIT` and no sorting at query time.
3. **License popularity.** Ranked license counts from the
   `license_counts` counter table, queried at consistency level `ONE`
   because a stale count in a read-only report costs nothing. The CRUD
   delete path uses `QUORUM` instead.

### Loading
Writes go out as prepared statements executed through the driver's
`execute_concurrent_with_args` helper with 64 requests in flight.
Prepared statements are parsed once and reused, and keeping requests
in flight avoids blocking on each round trip. Tables are truncated
before loading, which matters more here than in the other two sections
because counter columns accumulate and loading twice without truncating
would double every count.

## MongoDB Section (Part 2)

### Collections
```
commits    one document per commit, _id is the commit hash
           indexed on repo_name and author_name
repos      one document per repository with watch_count and name_length
           indexed on watch_count (descending) and name_length
licenses   one document per repository with its license
           indexed on license
```

### CRUD Operations
Create, Read, Update, and Delete on individual commit documents, keyed
by commit hash. Also includes a case-insensitive author search using a
regular expression query, which has no direct Redis equivalent without
building a dedicated index structure for it.

### Features
1. **Common words in commit messages.** An aggregation pipeline that
   lowercases each subject line, splits it into words with `$split`,
   flattens the result with `$unwind`, filters out stop words, then
   groups and sorts by frequency. All processing happens on the
   database server.
2. **Repository distribution by watch count.** Uses the `$bucket`
   aggregation stage to sort repositories into watch count ranges and
   count them, producing a histogram. Also lists the most watched
   repositories using the descending index on `watch_count`.
3. **Repository name analysis.** Reports average, minimum, and maximum
   repository name length using a `$group` aggregation with `$avg`,
   `$min`, and `$max`, then lists the longest and shortest repository
   names using the indexed `name_length` field.

## Redis Section (Part 1)

### Schema
```
commit:<commit_hash>              Hash        full commit record
commits:by_repo:<repo_name>       Set         commit hashes for that repo
commits:by_author:<repo_name>     Sorted Set  author name -> commit count
repos:loaded                      Set         every repo_name with commits loaded
languages:ranked                  Sorted Set  language name -> total bytes
licenses:ranked                   Sorted Set  license name -> repo count
```

### Features
1. **Language popularity**, ranked by total bytes of code across the
   dataset, read from a sorted set with `ZREVRANGE`.
2. **Commit activity by repository**, showing top contributors for any
   of the six loaded repositories.
3. **License popularity**, ranked by how many repositories use each
   license.

## Data Source Notes
- `Sample_Commits.json` supplies commit records for six well known
  repositories: torvalds/linux, apple/swift, twbs/bootstrap,
  facebook/react, Microsoft/vscode, and tensorflow/tensorflow.
- `Sample_Repos.json` supplies repository names with watch counts.
- `Licenses.json` supplies one license per repository.
- `Languages.json` is used only by the Redis section.
- `Files.json` and `Contents.json` are not used. Their repository names
  have almost no overlap with the commit data, and `Contents.json` is
  several hundred megabytes of raw file text that none of the
  implemented features require.
- The dataset contains no commit timestamps, so commit history is
  represented as activity by author rather than activity over time.

## Comparing All Five Databases

The point of building the same application five times is that each
database makes a different set of things easy and a different set hard.
Where they differ:

**Data modeling.** Redis required flattening each commit into a hash and
hand-building set and sorted-set structures for every lookup. MongoDB
stored each JSON record close to its original shape and added indexes
afterward. Cassandra kept a flat, typed row but deliberately stored the
same commit twice, because a query has to be served by a partition key.
Neo4j made the relationships themselves the data rather than pointers to
it. SQLite is the only one that stores each fact exactly once, because
it is the only one that can assemble a result from several tables at
query time instead of at load time.

**Denormalization.** Four of the five required it, in four different
forms: parallel index structures in Redis, duplicated tables in
Cassandra, a derived relationship in Neo4j, and embedded values in
MongoDB. Only the relational schema avoided it entirely. That is the
clearest single result of the whole project.

**Deletes.** Redis and Cassandra both required the application to clean
up every derived structure by hand and would silently leave orphans if
it forgot. Neo4j refused the delete outright until the relationships
were removed. SQLite removes dependent rows automatically through
`ON DELETE CASCADE`. MongoDB never had the problem, since the record was
self-contained to begin with.

**Analysis.** Redis and Cassandra had to precompute counts at write
time, by `ZINCRBY` and counter columns respectively. MongoDB aggregates
on the server but only within a single collection. Neo4j aggregates
during traversal, with cost proportional to how connected the starting
node is. SQLite composes aggregates freely: common table expressions
name intermediate results, `HAVING` filters on aggregates, and window
functions rank rows without collapsing them.

**Sorting.** Cassandra is the only one that stores rows physically
sorted on a chosen column, through clustering order, though that
ordering exists only inside a partition.

**Transactions.** Only SQLite offers a real multi-statement rollback
across several tables. Cassandra's logged batch guarantees eventual
application without isolation, and its lightweight transaction covers a
single partition. Redis, MongoDB, and Neo4j were each used with
single-operation writes in this project.

**Writes.** Cassandra `INSERT` is an upsert, so creating a record that
must not already exist needs `IF NOT EXISTS` and a Paxos round trip.
MongoDB rejects a duplicate `_id` outright. Redis and Neo4j both needed
an explicit existence check, Neo4j because `MERGE` would otherwise match
the existing node and overwrite it.

**Setup cost.** Four of the five needed a server running, and three of
those needed credentials configured before a single row could be read.
SQLite needed a writable folder.

**Queries only one of them can answer.** Each part surfaced one. Redis
could rank by score with no query language at all. MongoDB's regex
author search had no Cassandra equivalent without a table built for it
in advance. Cassandra's per-query consistency level has no counterpart
anywhere else. Neo4j's shortest path between two contributors has no
reasonable implementation in the other four, since the hop count is
unknown in advance. SQLite's per-group top-N in a single pass is
impractical everywhere else: `GROUP BY` alone collapses each group to
one row, and only a window function ranks within a group while leaving
the rows intact.

## Next Steps
The five database integrations that the project set out to build are
complete. If development continued, the following are the next items:

- Add a cross-database comparison view that runs the same logical query
  against all five databases and reports response times side by side.
  With five implementations finished there is finally enough variety for
  that measurement to say something.
- Add commit search filtered by repository across all five sections, so
  the same capability exists everywhere rather than in some sections
  only.
- Strengthen input validation on the CRUD menus, particularly commit
  hashes entered with inconsistent capitalization or surrounding
  whitespace.
- Offer a choice between reloading and appending at load time. Every
  loader currently clears its data first, which keeps loads repeatable
  but discards records created through the CRUD menus.
