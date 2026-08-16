# GitHub Archive Database Integration

A Python application that loads real GitHub Archive data into a NoSQL
database and performs CRUD operations and analysis on it.

The project is built in parts, one database per part:

| Part | Database | Type |
|------|----------|------|
| 1 | **Redis** | Key-value store |
| 2 | **MongoDB** | Document store |
| 3 | **Cassandra** | Column-family store |

All three implementations live in the same project so the same
application can be run against each one and the three data models
compared side by side.

## Dependencies
- Python 3.10 or later
- Cassandra node (for the Cassandra section)
- MongoDB server (for the MongoDB section)
- Redis server (for the Redis section)
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
3. Start Cassandra, MongoDB, and/or Redis depending on which section
   you plan to use.
4. If Cassandra is running with the `PasswordAuthenticator` enabled,
   set the role name and password in `cassandra_config.py`. If it is
   running with `AllowAllAuthenticator`, set `USE_AUTH = False` there
   instead.
5. Create a `data/` folder in the project root and place the dataset
   files inside it.
6. Run the application: `python main.py`
7. Choose a database, then choose option 1 to load data before using
   CRUD or any feature. Every other option reads from what the load
   step creates.

The Cassandra keyspace and tables are created automatically on first
connection, so no manual `cqlsh` setup is required.

## Project Structure
```
redis-github-archive/
├── main.py                                # Entry point, database selection menu
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

## Redis vs MongoDB vs Cassandra, Observed Differences

**Data modeling.** Redis required flattening each commit into a hash
and hand-building set and sorted-set structures for every lookup.
MongoDB stored each JSON record close to its original shape, nested
fields included, and added indexes afterward. Cassandra sits between
the two but for a different reason: the row shape is flat and typed
like a relational table, yet the same commit is deliberately stored
twice, because a query has to be served by a partition key and there is
no index that makes an unplanned query cheap.

**Deletes.** MongoDB is one `delete_one` call. Redis and Cassandra both
require cleaning up every derived structure the record was written
into, or the extra tables and indexes are left pointing at rows that no
longer exist.

**Analysis.** MongoDB performs grouping, bucketing, and sorting on the
server through the aggregation pipeline. Neither Redis nor Cassandra
has server-side aggregation, so both had to precompute counts during
loading. The mechanism differs: Redis uses `ZINCRBY` into a sorted set,
which keeps the results ranked, while Cassandra uses counter columns,
which cannot be clustering columns and therefore come back unordered
and are ranked in the application.

**Sorting.** Cassandra is the only one of the three that can store rows
physically sorted on a chosen column. The clustering order on
`repos_by_watch_tier` means the most watched repositories in a tier
come off disk already ordered, but that ordering only exists inside a
partition, which is why the top-N-overall query walks the tiers from
the highest down rather than issuing one query.

**Consistency.** Redis and MongoDB were used with defaults. Cassandra
makes consistency a per-query decision, so the read-only report queries
run at `ONE` and the CRUD delete runs at `QUORUM`.

**Writes.** Cassandra `INSERT` is an upsert, so creating a record that
must not already exist needs `IF NOT EXISTS` and the Paxos round trip
that comes with it. MongoDB rejects a duplicate `_id` outright, and
Redis needed an explicit existence check.

## Next Steps
- Add a cross-database comparison view that runs the same query against
  all three databases and reports response times.
- Add commit search filtered by repository across all three sections.
- Strengthen input validation on the CRUD menus, particularly commit
  hashes entered with inconsistent capitalization or surrounding
  whitespace.
