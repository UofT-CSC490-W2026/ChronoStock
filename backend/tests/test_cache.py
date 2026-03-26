import json
from types import SimpleNamespace
import sys
import pytest

from app import cache


def test_local_set_and_get_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path)

    cache._local_set("stock:NVDA:1Y", {"x": 1})
    assert cache._local_get("stock:NVDA:1Y") == {"x": 1}


def test_local_get_missing_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path)
    assert cache._local_get("missing:key") is None


def test_redis_track_and_evict_removes_oldest(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 2)

    class FakePipeline:
        def __init__(self, client):
            self.client = client
            self.ops = []

        def zadd(self, key, payload):
            self.ops.append(("zadd", key, payload))
            return self

        def zcard(self, key):
            self.ops.append(("zcard", key))
            return self

        def delete(self, *keys):
            self.ops.append(("delete", keys))
            return self

        def zrem(self, key, *members):
            self.ops.append(("zrem", key, members))
            return self

        def execute(self):
            # First pipeline call returns (_, count).
            if any(op[0] == "zcard" for op in self.ops):
                return [None, self.client.cardinality]
            self.client.deleted = list(self.ops)
            return []

    class FakeClient:
        def __init__(self):
            self.cardinality = 4
            self.deleted = []

        def pipeline(self):
            return FakePipeline(self)

        def zrange(self, key, start, end):
            assert start == 0
            assert end == 1
            return ["k:1", "k:2"]

    client = FakeClient()
    cache._redis_track_and_evict(client, "k:new")

    op_names = [op[0] for op in client.deleted]
    assert "delete" in op_names
    assert "zrem" in op_names


def test_redis_get_miss_cleans_index_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 10)

    class FakeClient:
        def __init__(self):
            self.removed = []

        def get(self, _key):
            return None

        def zrem(self, index_key, redis_key):
            self.removed.append((index_key, redis_key))

    fake = FakeClient()
    monkeypatch.setattr(cache, "_redis_client", lambda: fake)

    assert cache._redis_get("abc") is None
    assert len(fake.removed) == 1


def test_redis_get_valid_json_updates_lru(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 10)

    class FakeClient:
        def __init__(self):
            self.zadd_calls = []

        def get(self, _key):
            return json.dumps({"ok": True})

        def zadd(self, index_key, payload):
            self.zadd_calls.append((index_key, payload))

    fake = FakeClient()
    monkeypatch.setattr(cache, "_redis_client", lambda: fake)

    assert cache._redis_get("abc") == {"ok": True}
    assert len(fake.zadd_calls) == 1


def test_redis_get_invalid_json_returns_none(monkeypatch) -> None:
    class FakeClient:
        def get(self, _key):
            return "{bad json"

        def zadd(self, _index_key, _payload):
            return None

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
    fake_redis = SimpleNamespace(
        Redis=SimpleNamespace(
            from_url=lambda url, decode_responses=True: calls.append((url, decode_responses)) or "redis-client"
        )
    )
    original = sys.modules.get("redis")
    sys.modules["redis"] = fake_redis
    try:
        assert cache._redis_client() == "redis-client"
    finally:
        if original is None:
            del sys.modules["redis"]
        else:
            sys.modules["redis"] = original

    assert calls == [(cache.REDIS_URL, True)]


def test_redis_track_and_evict_returns_early_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 0)

    class FakeClient:
        def pipeline(self):
            raise AssertionError("should not call pipeline")

    cache._redis_track_and_evict(FakeClient(), "redis:key")


def test_redis_track_and_evict_returns_when_not_over_limit(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 3)

    class FakePipeline:
        def zadd(self, key, payload):
            return self

        def zcard(self, key):
            return self

        def execute(self):
            return [None, 3]

    class FakeClient:
        def pipeline(self):
            return FakePipeline()

        def zrange(self, *args):
            raise AssertionError("should not fetch oldest keys")

    cache._redis_track_and_evict(FakeClient(), "redis:key")


def test_redis_track_and_evict_returns_when_oldest_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 1)

    class FakePipeline:
        def zadd(self, key, payload):
            return self

        def zcard(self, key):
            return self

        def execute(self):
            return [None, 2]

    class FakeClient:
        def pipeline(self):
            return FakePipeline()

        def zrange(self, key, start, end):
            return []

    cache._redis_track_and_evict(FakeClient(), "redis:key")


def test_redis_set_without_ttl_and_error_paths(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_CACHE_TTL_SECONDS", 0)
    track_calls = []

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
    monkeypatch.setattr(cache, "_redis_track_and_evict", lambda c, key: track_calls.append((c, key)))

    cache._redis_set("abc", {"ok": True})
    assert client.calls == [(cache._redis_key("abc"), {"ok": True}, None)]
    assert track_calls == [(client, cache._redis_key("abc"))]

    class BadClient:
        def set(self, key, payload, ex=None):
            raise FakeRedisError("down")

    monkeypatch.setattr(cache, "_redis_client", lambda: BadClient())
    cache._redis_set("abc", {"ok": True})


def test_redis_get_paths_when_index_tracking_disabled(monkeypatch) -> None:
    monkeypatch.setattr(cache, "REDIS_MAX_KEYS", 0)

    class MissingClient:
        def get(self, _key):
            return None

    monkeypatch.setattr(cache, "_redis_client", lambda: MissingClient())
    assert cache._redis_get("abc") is None

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
    track_calls = []

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
    monkeypatch.setattr(cache, "_redis_track_and_evict", lambda c, key: track_calls.append((c, key)))

    cache._redis_set("abc", {"ok": True})

    assert client.calls == [(cache._redis_key("abc"), {"ok": True}, 30)]
    assert track_calls == [(client, cache._redis_key("abc"))]
