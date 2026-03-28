import json
from types import SimpleNamespace
import sys
import pytest

from app import cache


def test_l1_set_evicts_oldest_and_l1_get_moves_to_end(monkeypatch) -> None:
    original_max = cache._L1_MAX_SIZE
    original_cache = cache._l1_cache.copy()
    try:
        monkeypatch.setattr(cache, "_L1_MAX_SIZE", 2)
        cache._l1_cache.clear()

        cache._l1_set("a", 1)
        cache._l1_set("b", 2)
        hit, value = cache._l1_get("a")
        assert hit is True
        assert value == 1

        cache._l1_set("c", 3)
        assert list(cache._l1_cache.keys()) == ["a", "c"]
    finally:
        cache._l1_cache.clear()
        cache._l1_cache.update(original_cache)
        monkeypatch.setattr(cache, "_L1_MAX_SIZE", original_max)


def test_local_set_and_get_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path)

    cache._local_set("stock:NVDA:1Y", {"x": 1})
    assert cache._local_get("stock:NVDA:1Y") == {"x": 1}


def test_local_get_missing_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path)
    assert cache._local_get("missing:key") is None


def test_redis_get_invalid_json_returns_none(monkeypatch) -> None:
    class FakeClient:
        def get(self, _key):
            return "{bad json"

    monkeypatch.setattr(cache, "_redis_client", lambda: FakeClient())
    assert cache._redis_get("abc") is None


def test_get_and_set_dispatch_by_backend(monkeypatch) -> None:
    monkeypatch.setattr(cache, "CACHE_BACKEND", "s3")
    monkeypatch.setattr(cache, "_s3_get", lambda key: {"src": "s3", "key": key})
    seen = {}
    monkeypatch.setattr(cache, "_s3_set", lambda key, value: seen.update({"k": key, "v": value}))

    assert cache.get("k1") == {"src": "s3", "key": "k1"}
    cache.set("k1", {"a": 1})
    assert seen == {"k": "k1", "v": {"a": 1}}

    monkeypatch.setattr(cache, "CACHE_BACKEND", "redis")
    monkeypatch.setattr(cache, "_redis_get", lambda key: {"src": "redis", "key": key})
    seen.clear()
    monkeypatch.setattr(cache, "_redis_set", lambda key, value: seen.update({"k": key, "v": value}))

    assert cache.get("k2") == {"src": "redis", "key": "k2"}
    cache.set("k2", {"b": 2})
    assert seen == {"k": "k2", "v": {"b": 2}}


def test_get_and_set_dispatch_to_local_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "CACHE_BACKEND", "local")
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path)

    cache.set("k3", {"c": 3})
    assert cache.get("k3") == {"c": 3}


def test_get_backend_miss_does_not_populate_l1(monkeypatch) -> None:
    original_cache = cache._l1_cache.copy()
    try:
        cache._l1_cache.clear()
        monkeypatch.setattr(cache, "CACHE_BACKEND", "local")
        monkeypatch.setattr(cache, "_local_get", lambda key: None)

        assert cache.get("missing") is None
        assert "missing" not in cache._l1_cache
    finally:
        cache._l1_cache.clear()
        cache._l1_cache.update(original_cache)


def test_s3_client_builds_boto3_client() -> None:
    calls = []
    fake_boto3 = SimpleNamespace(client=lambda service: calls.append(service) or "s3-client")
    original = sys.modules.get("boto3")
    sys.modules["boto3"] = fake_boto3
    try:
        assert cache._s3_client() == "s3-client"
    finally:
        if original is None:
            del sys.modules["boto3"]
        else:
            sys.modules["boto3"] = original

    assert calls == ["s3"]


def test_s3_get_returns_none_for_missing_key(monkeypatch) -> None:
    class FakeClientError(Exception):
        def __init__(self, code):
            self.response = {"Error": {"Code": code}}

    class FakeS3:
        def get_object(self, Bucket, Key):
            raise FakeClientError("NoSuchKey")

    botocore_exceptions = SimpleNamespace(ClientError=FakeClientError)
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(exceptions=botocore_exceptions))
    monkeypatch.setitem(sys.modules, "botocore.exceptions", botocore_exceptions)
    monkeypatch.setattr(cache, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(cache, "S3_BUCKET", "bucket")
    monkeypatch.setattr(cache, "S3_PREFIX", "prefix/")

    assert cache._s3_get("abc") is None


def test_s3_get_reraises_non_missing_client_error(monkeypatch) -> None:
    class FakeClientError(Exception):
        def __init__(self, code):
            self.response = {"Error": {"Code": code}}

    class FakeS3:
        def get_object(self, Bucket, Key):
            raise FakeClientError("403")

    botocore_exceptions = SimpleNamespace(ClientError=FakeClientError)
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(exceptions=botocore_exceptions))
    monkeypatch.setitem(sys.modules, "botocore.exceptions", botocore_exceptions)
    monkeypatch.setattr(cache, "_s3_client", lambda: FakeS3())

    with pytest.raises(FakeClientError):
        cache._s3_get("abc")


def test_s3_set_writes_json_payload(monkeypatch) -> None:
    seen = {}

    class FakeS3:
        def put_object(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(cache, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(cache, "S3_BUCKET", "bucket")
    monkeypatch.setattr(cache, "S3_PREFIX", "prefix/")

    cache._s3_set("abc", {"x": 1})
    assert seen["Bucket"] == "bucket"
    assert seen["Key"] == "prefix/abc.json"
    assert json.loads(seen["Body"]) == {"x": 1}


def test_s3_get_reads_json_payload(monkeypatch) -> None:
    class FakeBody:
        def read(self):
            return b'{"ok": true}'

    class FakeS3:
        def get_object(self, Bucket, Key):
            return {"Body": FakeBody()}

    monkeypatch.setattr(cache, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(cache, "S3_BUCKET", "bucket")
    monkeypatch.setattr(cache, "S3_PREFIX", "prefix/")

    assert cache._s3_get("abc") == {"ok": True}


def test_redis_client_uses_from_url() -> None:
    calls = []

    class FakeConnectionPool:
        @staticmethod
        def from_url(url, decode_responses=True):
            calls.append((url, decode_responses))
            return "pool"

    class FakeRedis:
        def __init__(self, connection_pool=None):
            self.connection_pool = connection_pool

    fake_redis = SimpleNamespace(ConnectionPool=FakeConnectionPool, Redis=FakeRedis)
    original = sys.modules.get("redis")
    sys.modules["redis"] = fake_redis
    try:
        # First call should create the pool via ConnectionPool.from_url(...)
        client = cache._redis_client()
        assert isinstance(client, FakeRedis)
        assert client.connection_pool == "pool"
    finally:
        if original is None:
            del sys.modules["redis"]
        else:
            sys.modules["redis"] = original

    assert calls == [(cache.REDIS_URL, True)]


def test_get_pool_reuses_existing_pool(monkeypatch) -> None:
    original_pool = cache._redis_pool
    cache._redis_pool = "existing-pool"
    try:
        assert cache._get_pool() == "existing-pool"
    finally:
        cache._redis_pool = original_pool


def test_redis_set_without_ttl_and_error_paths(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_CACHE_TTL_SECONDS", 0)

    class FakeRedisError(Exception):
        pass

    class FakeClient:
        def __init__(self):
            self.calls = []

        def set(self, key, payload, ex=None):
            self.calls.append((key, json.loads(payload), ex))

    client = FakeClient()
    redis_exceptions = SimpleNamespace(RedisError=FakeRedisError)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(exceptions=redis_exceptions))
    monkeypatch.setitem(sys.modules, "redis.exceptions", redis_exceptions)
    monkeypatch.setattr(cache, "_redis_client", lambda: client)

    cache._redis_set("abc", {"ok": True})
    assert client.calls == [(cache.REDIS_PREFIX + "abc", {"ok": True}, None)]

    class BadClient:
        def set(self, key, payload, ex=None):
            raise FakeRedisError("down")

    monkeypatch.setattr(cache, "_redis_client", lambda: BadClient())
    cache._redis_set("abc", {"ok": True})


def test_redis_get_miss_returns_none(monkeypatch) -> None:
    class MissingClient:
        def get(self, _key):
            return None

    monkeypatch.setattr(cache, "_redis_client", lambda: MissingClient())
    assert cache._redis_get("abc") is None


def test_redis_get_hit_returns_dict(monkeypatch) -> None:
    class HitClient:
        def get(self, _key):
            return json.dumps({"ok": True})

    monkeypatch.setattr(cache, "_redis_client", lambda: HitClient())
    assert cache._redis_get("abc") == {"ok": True}


def test_redis_get_returns_none_on_redis_error(monkeypatch) -> None:
    class FakeRedisError(Exception):
        pass

    class BadClient:
        def get(self, _key):
            raise FakeRedisError("down")

    redis_exceptions = SimpleNamespace(RedisError=FakeRedisError)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(exceptions=redis_exceptions))
    monkeypatch.setitem(sys.modules, "redis.exceptions", redis_exceptions)
    monkeypatch.setattr(cache, "_redis_client", lambda: BadClient())

    assert cache._redis_get("abc") is None


def test_redis_set_uses_ttl_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_CACHE_TTL_SECONDS", 30)

    class FakeRedisError(Exception):
        pass

    class FakeClient:
        def __init__(self):
            self.calls = []

        def set(self, key, payload, ex=None):
            self.calls.append((key, json.loads(payload), ex))

    client = FakeClient()
    redis_exceptions = SimpleNamespace(RedisError=FakeRedisError)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(exceptions=redis_exceptions))
    monkeypatch.setitem(sys.modules, "redis.exceptions", redis_exceptions)
    monkeypatch.setattr(cache, "_redis_client", lambda: client)

    cache._redis_set("abc", {"ok": True})

    assert client.calls == [(cache.REDIS_PREFIX + "abc", {"ok": True}, 30)]
