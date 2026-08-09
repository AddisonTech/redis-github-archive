# GitHub Archive Database Integration

A Python application that loads real GitHub Archive data into a database
and performs CRUD operations and analysis on it.

The project is built in parts. Part 1 implemented the application
against **Redis**, a key-value store. Part 2 implements comparable
functionality against **MongoDB**, a document store. Both are included
so the two approaches can be run and compared side by side.

## Dependencies
- Python 3.10 or later
- MongoDB server (for the MongoDB section)
- Redis server (for the Redis section)
- pymongo (`pip install pymongo`)
- redis-py (`pip install redis`)
- matplotlib (`pip install matplotlib`), required by the Redis commit
  activity feature, which renders a bar chart of top contributors

Install everything at once with:
```
pip install -r requirements.txt
```

## Technology Requirements
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
3. Start MongoDB and/or Redis depending on which section you plan to use.
4. Create a `data/` folder in the project root and place the dataset
   files inside it.
5. Run the application: `python main.py`
6. Choose a database, then choose option 1 to load data before using
   CRUD or any feature. Every other option reads from what the load
   step creates.

## Project Structure
```
redis-github-archive/
├── main.py                         # Entry point, database selection menu
│
├── mongo_config.py                 # MongoDB connection settings
├── mongo_data_loader.py            # Loads dataset into MongoDB collections
├── mongo_crud.py                   # CRUD on commit documents
├── feature_commit_words.py         # MongoDB feature 1
├── feature_watch_distribution.py   # MongoDB feature 2
├── feature_repo_names.py           # MongoDB feature 3
│
├── redis_config.py                 # Redis connection settings
├── data_loader.py                  # Loads dataset into Redis
├── crud_operations.py              # CRUD on commit records
├── feature_language_stats.py       # Redis feature 1
├── feature_commit_activity.py      # Redis feature 2
├── feature_license_stats.py        # Redis feature 3
│
└── requirements.txt
```

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

## Redis vs MongoDB, Observed Differences
Building the same application on both databases surfaced some concrete
trade-offs:

- **Data modeling.** Redis required flattening each commit into a hash
  and hand-building separate set and sorted-set structures to support
  lookups. MongoDB stored each JSON record close to its original shape,
  nested fields included.
- **Deletes.** Deleting a commit in Redis meant also removing it from
  its repo set and decrementing its author sorted set, or the indexes
  would be left with orphaned references. In MongoDB it is a single
  `delete_one` call.
- **Analysis.** Redis has no server-side aggregation, so analysis
  either had to be precomputed during loading or pulled back into
  Python and tallied there. MongoDB's aggregation pipeline performs
  grouping, bucketing, and sorting on the server and returns only the
  finished result.
- **Querying.** Redis can only look up what it was explicitly indexed
  for. MongoDB can query inside documents, which is what makes the
  author search feature possible without extra load-time work.

## Next Steps
- (Update this section each week with what's left to do)
