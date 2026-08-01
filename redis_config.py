"""
redis_config.py
Shared Redis connection setup used by every other module in this project.
Nobody should need to touch this file unless the connection settings change
(for example, if you move from a local Redis instance to a hosted one).
"""

import redis

# Update these values if your Redis instance runs somewhere other than
# localhost, or if it requires a password.
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0


def get_redis_connection():
    """
    Returns a Redis connection object that the rest of the app can use.
    decode_responses=True means values come back as normal Python strings
    instead of bytes, which makes JSON handling much easier.
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )


if __name__ == "__main__":
    # Quick sanity check: run this file directly to confirm Redis is
    # reachable before anyone starts building on top of it.
    r = get_redis_connection()
    try:
        r.ping()
        print("Connected to Redis successfully.")
    except redis.exceptions.ConnectionError:
        print("Could not connect to Redis. Is the server running?")
