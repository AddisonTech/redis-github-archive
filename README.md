# GitHub Archive Redis Integration

A Python application that loads real GitHub commit, language, and
license data into Redis and performs CRUD operations and analysis on
it.

## Dependencies
- Python 3.10 or later
- Redis server (running locally or accessible remotely)
- redis-py (`pip install redis`)
- matplotlib, only needed if you switch the commit activity feature
  from text bars to an actual chart

Install everything at once with:
```
pip install -r requirements.txt
```

## Technology Requirements
- A running Redis instance.
- The dataset files, placed in a `data/` folder in the project root:
  `Sample_Commits.json`, `Languages.json`, `Licenses.json`

Note: the dataset files are not committed to this repository. They're
several hundred megabytes combined, which exceeds GitHub's per-file
size limits and isn't something you want tracked in version control
anyway. Only the code is pushed; the `data/` folder is listed in
`.gitignore`.

## Setup
1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Make sure your Redis server is running.
4. Create a `data/` folder in the project root and place
   `Sample_Commits.json`, `Languages.json`, and `Licenses.json` inside
   it.
5. Run the application: `python main.py`
6. From the menu, choose option 1 to load data into Redis before using
   any CRUD or feature options. The language file has a few million
   lines, so this step can take a couple of minutes; progress prints
   let you know it's still working.

## Project Structure
```
redis-github-archive/
├── main.py                      # Entry point and menu, ties everything together
├── redis_config.py              # Shared Redis connection setup
├── data_loader.py                # Reads the dataset files and loads them into Redis
├── crud_operations.py            # Create, Read, Update, Delete on commit records
├── feature_language_stats.py     # Feature 1: language popularity by total bytes
├── feature_commit_activity.py    # Feature 2: commit activity by author, per repo
├── feature_license_stats.py      # Feature 3: license popularity by repo count
└── requirements.txt
```

## Data Source and Design Decisions
This project uses three of the provided dataset files:
- `Sample_Commits.json`, real commit records (with file-change data)
  for six well-known repositories: torvalds/linux, apple/swift,
  twbs/bootstrap, facebook/react, Microsoft/vscode, and
  tensorflow/tensorflow. This is the CRUD entity.
- `Languages.json`, aggregated into a total-bytes-per-language
  leaderboard.
- `Licenses.json`, aggregated into a repo-count-per-license
  leaderboard.

`Files.json` and `Contents.json` were left out. Their repo names
barely overlap with the other files (each is an independent random
sample from the course dataset), and `Contents.json` alone is
hundreds of megabytes of raw file text that none of the three
features need.

The dataset has no commit timestamps, so "commit history" is
represented as commit activity by author rather than activity over
time.

## Redis Schema
```
commit:<commit_hash>              Hash        full commit record
commits:by_repo:<repo_name>       Set         commit hashes for that repo
commits:by_author:<repo_name>     Sorted Set  author name -> commit count
repos:loaded                      Set         every repo_name with commits loaded

languages:ranked                  Sorted Set  language name -> total bytes
licenses:ranked                   Sorted Set  license name -> repo count
```

## Current Features
1. CRUD operations on commit records
2. Language popularity across the full dataset, ranked by total bytes
3. Commit activity by author, for any of the six loaded repositories
4. License popularity across the dataset, ranked by repo count

## Next Steps
- (Update this section each week with what's left to do)
