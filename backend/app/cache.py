"""
File-based persistent cache.

Local dev  : JSON files written to ./cache/ on disk.
AWS deploy : JSON files written to an S3 bucket (set CACHE_BACKEND=s3).
Redis      : JSON values written to Redis (set CACHE_BACKEND=redis).

For Redis, keys can be bounded with TTL + optional max-key eviction.
To force a refresh, delete the file/object/key for the backend in use.
"""
import json
import os
import time
from pathlib import Path
from typing import Any

CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "local")
LOCAL_CACHE_DIR = Path(os.environ.get("LOCAL_CACHE_DIR", "./cache"))
S3_BUCKET = os.environ.get("S3_CACHE_BUCKET", "")
S3_PREFIX = os.environ.get("S3_CACHE_PREFIX", "chronostock/cache/")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.environ.get("REDIS_CACHE_PREFIX", "chronostock:cache:")
REDIS_CACHE_TTL_SECONDS = int(os.environ.get("REDIS_CACHE_TTL_SECONDS", "86400"))
REDIS_MAX_KEYS = int(os.environ.get("REDIS_MAX_KEYS", "5000"))


def _filename(key: str) -> str:
    """Turn a cache key like 'stock:AAPL:1Y' into 'stock_AAPL_1Y.json'."""
    return key.replace(":", "_") + ".json"


# ── Local disk ────────────────────────────────────────────────────────────────

def _local_get(key: str) -> Any | None:
    path = LOCAL_CACHE_DIR / _filename(key)
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def _local_set(key: str, value: Any) -> None:
    LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_CACHE_DIR / _filename(key)
    with path.open("w") as f:
        json.dump(value, f)


# ── S3 ────────────────────────────────────────────────────────────────────────

def _s3_client():
    import boto3  # type: ignore
    return boto3.client("s3")


def _s3_get(key: str) -> Any | None:
    import botocore.exceptions  # type: ignore
    try:
        obj = _s3_client().get_object(Bucket=S3_BUCKET, Key=S3_PREFIX + _filename(key))
        return json.loads(obj["Body"].read())
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def _s3_set(key: str, value: Any) -> None:
    _s3_client().put_object(
        Bucket=S3_BUCKET,
        Key=S3_PREFIX + _filename(key),
        Body=json.dumps(value),
        ContentType="application/json",
    )


# ── Redis ─────────────────────────────────────────────────────────────────────

def _redis_client():
    import redis  # type: ignore
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _redis_key(key: str) -> str:
    return REDIS_PREFIX + key


def _redis_index_key() -> str:
    return REDIS_PREFIX + "__lru_index__"


def _redis_track_and_evict(client: Any, redis_key: str) -> None:
    """Track key recency and evict oldest keys when the cap is exceeded."""
    if REDIS_MAX_KEYS <= 0:
        return

    index_key = _redis_index_key()
    now = time.time()

    # Update recency + read cardinality in one round trip.
    pipe = client.pipeline()
    pipe.zadd(index_key, {redis_key: now})
    pipe.zcard(index_key)
    _, count = pipe.execute()

    overflow = count - REDIS_MAX_KEYS
    if overflow <= 0:
        return

    oldest = client.zrange(index_key, 0, overflow - 1)
    if not oldest:
        return

    pipe = client.pipeline()
    pipe.delete(*oldest)
    pipe.zrem(index_key, *oldest)
    pipe.execute()


def _redis_get(key: str) -> Any | None:
    import redis.exceptions  # type: ignore
    try:
        client = _redis_client()
        redis_key = _redis_key(key)
        raw = client.get(redis_key)
        if raw is None:
            if REDIS_MAX_KEYS > 0:
                client.zrem(_redis_index_key(), redis_key)
            return None
        if REDIS_MAX_KEYS > 0:
            client.zadd(_redis_index_key(), {redis_key: time.time()})
        return json.loads(raw)
    except (redis.exceptions.RedisError, json.JSONDecodeError):
        return None


def _redis_set(key: str, value: Any) -> None:
    import redis.exceptions  # type: ignore
    try:
        client = _redis_client()
        redis_key = _redis_key(key)
        payload = json.dumps(value)

        if REDIS_CACHE_TTL_SECONDS > 0:
            client.set(redis_key, payload, ex=REDIS_CACHE_TTL_SECONDS)
        else:
            client.set(redis_key, payload)

        _redis_track_and_evict(client, redis_key)
    except redis.exceptions.RedisError:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str) -> Any | None:
    if CACHE_BACKEND == "s3":
        return _s3_get(key)
    elif CACHE_BACKEND == "redis":
        return _redis_get(key)
    else:
        return _local_get(key)


def set(key: str, value: Any) -> None:
    if CACHE_BACKEND == "s3":
        _s3_set(key, value)
        return
    elif CACHE_BACKEND == "redis":
        _redis_set(key, value)
        return
    else:
        _local_set(key, value)
