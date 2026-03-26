"""
File-based persistent cache.

Local dev  : JSON files written to ./cache/ on disk.
AWS deploy : JSON files written to an S3 bucket (set CACHE_BACKEND=s3).
Redis      : JSON values written to Redis (set CACHE_BACKEND=redis).
"""
import json
import os
from pathlib import Path
from typing import Any

CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "local")
LOCAL_CACHE_DIR = Path(os.environ.get("LOCAL_CACHE_DIR", "./cache"))
S3_BUCKET = os.environ.get("S3_CACHE_BUCKET", "")
S3_PREFIX = os.environ.get("S3_CACHE_PREFIX", "chronostock/cache/")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.environ.get("REDIS_CACHE_PREFIX", "chronostock/cache/")
REDIS_CACHE_TTL_SECONDS = int(os.environ.get("REDIS_CACHE_TTL_SECONDS", "86400"))


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

_redis_pool = None


def _get_pool():
    global _redis_pool
    if _redis_pool is None:
        import redis
        _redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
    return _redis_pool


def _redis_client():
    import redis
    return redis.Redis(connection_pool=_get_pool())


def _redis_get(key: str) -> Any | None:
    import redis.exceptions
    try:
        raw = _redis_client().get(REDIS_PREFIX + key)
        return json.loads(raw) if raw is not None else None
    except (redis.exceptions.RedisError, json.JSONDecodeError):
        return None


def _redis_set(key: str, value: Any) -> None:
    import redis.exceptions
    try:
        _redis_client().set(
            REDIS_PREFIX + key,
            json.dumps(value),
            ex=REDIS_CACHE_TTL_SECONDS if REDIS_CACHE_TTL_SECONDS > 0 else None,
        )
    except redis.exceptions.RedisError:
        pass


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