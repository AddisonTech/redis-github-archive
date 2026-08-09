"""
feature_commit_words.py

Feature 1: finds the most common words used in commit messages across
the dataset.

This is implemented entirely as a MongoDB aggregation pipeline, which
is the point of the feature. The whole word split, filter, group, and
sort happens on the database server; Python only receives the finished
top-N list. The Redis version of this project had to pull values back
into Python and tally them with collections.Counter because Redis has
no server-side equivalent.

Pipeline stages used:
    $project    reduce each document to just its lowercased subject line
    $split      break the subject into an array of words
    $unwind     turn each element of that array into its own document
    $match      drop common filler words and anything under three characters
    $group      count occurrences of each remaining word
    $sort       order by count, highest first
    $limit      keep only the top N
"""

from mongo_config import get_database, COMMITS_COLLECTION

# Common English and Git filler words that would otherwise dominate the
# results without saying anything about what the commits actually did.
STOP_WORDS = [
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at",
    "is", "it", "be", "as", "by", "with", "from", "that", "this", "was",
    "are", "not", "but", "if", "when", "we", "i", "you", "so", "into",
    "up", "out", "no", "do", "can", "has", "have", "had", "will", "-",
    "*", "+", "=", "|", "&", "",
]


def get_top_words(top_n=15):
    """
    Runs the aggregation pipeline and returns a list of
    (word, count) tuples, most frequent first.
    """
    db = get_database()

    pipeline = [
        # Lowercase the subject so "Fix" and "fix" count as one word
        {"$project": {"subject_lower": {"$toLower": "$subject"}}},
        # Split the sentence into individual words on spaces
        {"$project": {"words": {"$split": ["$subject_lower", " "]}}},
        # Flatten the array so each word becomes its own document
        {"$unwind": "$words"},
        # Drop filler words, then require at least three characters so
        # stray punctuation and abbreviations don't crowd the results
        {"$match": {"words": {"$nin": STOP_WORDS, "$regex": "^.{3,}$"}}},
        # Tally each distinct word
        {"$group": {"_id": "$words", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]

    results = db[COMMITS_COLLECTION].aggregate(pipeline)
    return [(doc["_id"], doc["count"]) for doc in results]


def print_word_report(top_n=15):
    """
    Prints the most common commit message words as a text bar chart.
    This is what main.py calls when the user picks this feature.
    """
    results = get_top_words(top_n)

    print(f"\nTop {top_n} Words in Commit Messages:")
    if not results:
        print("  No data found. Has the data been loaded yet?")
        return

    max_count = results[0][1]
    for rank, (word, count) in enumerate(results, start=1):
        bar_length = int((count / max_count) * 35) if max_count else 0
        print(f"  {rank:>2}. {word[:20]:<20} {'#' * bar_length} ({count:,})")


if __name__ == "__main__":
    print_word_report()
