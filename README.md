# GitHub Archive Redis Integration

A Python application that loads GitHub Archive event data into Redis and
performs CRUD operations and data analysis on it.

## Team Members
- Person 1: Data loading and Redis schema
- Person 2: CRUD operations and CLI
- Person 3: Feature - language/technology popularity analysis
- Person 4: Feature - commit history visualization, integration

## Dependencies
- Python 3.10 or later
- Redis server (running locally or accessible remotely)
- redis-py (`pip install redis`)
- matplotlib (`pip install matplotlib`), only needed if using the chart
  version of the commit history feature

Install everything at once with:
```
pip install -r requirements.txt
```

## Technology Requirements
- A running Redis instance. See the course's "Add a Linux User and
  Create a GitHub Repo" resource for setup if you don't already have
  one available.
- The GitHubArchive-Dataset.zip file, unzipped into a folder named
  `data/` in the project root (or update the path in `main.py`).

## Setup
1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Make sure your Redis server is running.
4. Unzip the GitHubArchive dataset into a `data/` folder in the
   project root.
5. Run the application: `python main.py`

## Project Structure
```
redis-github-archive/
├── main.py                    # Entry point and menu, ties everything together
├── redis_config.py            # Shared Redis connection setup
├── data_loader.py             # Reads JSON data and loads it into Redis
├── crud_operations.py         # Create, Read, Update, Delete on event records
├── feature_language_stats.py  # Feature: language/technology popularity
├── feature_commit_viz.py      # Feature: commit history visualization
└── requirements.txt
```

## Current Features
- CRUD operations on GitHub event records stored in Redis
- Language/technology popularity analysis across the dataset
- Commit history visualization by day, optionally filtered by repo

## Next Steps
- (Update this section each week with what's left to do)
