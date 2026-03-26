import argparse
import builtins
import random
from pathlib import Path
import textwrap
from types import SimpleNamespace

from app import benchmark


def test_build_keys_and_payload_are_deterministic() -> None:
    keys = benchmark._build_keys(3)
    payload = benchmark._build_payload("TK0001", 2, random.Random(42))

    assert keys == ["bench:stock:TK0000", "bench:stock:TK0001", "bench:stock:TK0002"]
    assert payload["ticker"] == "TK0001"
    assert payload["companyName"] == "TK0001 Corp"
    assert len(payload["bars"]) == 2
    assert payload["bars"][0]["time"] == "2018-01-01"
    assert payload["events"] == []


def test_parse_args_reads_defaults_and_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "cache", "--backend", "s3", "--keys", "9", "--cleanup", "--child"],
    )

    args = benchmark._parse_args()

    assert args.benchmark == "cache"
    assert args.backend == "s3"
    assert args.keys == 9
    assert args.cleanup is True
    assert args.child is True


def test_percentile_stats_and_format() -> None:
    assert benchmark._percentile([], 0.5) == 0.0
    assert benchmark._percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0

    stats = benchmark._stats([4.0, 1.0, 3.0, 2.0])
    assert stats["count"] == 4.0
    assert stats["mean_ms"] == 2.5
    assert stats["50th_percentile_ms"] == 3.0

    line = benchmark._format_stats("warm", [1.0, 2.0, 3.0])
    assert "warm" in line
    assert "count=3" in line
    assert "mean=2.000ms" in line


def test_cleanup_cache_keys_local_and_redis(tmp_path) -> None:
    local_dir = tmp_path / "cache"
    local_dir.mkdir()
    file_a = local_dir / "a.json"
    file_a.write_text("{}", encoding="utf-8")

    local_cache = SimpleNamespace(
        LOCAL_CACHE_DIR=local_dir,
        _filename=lambda key: "a.json" if key == "k1" else "missing.json",
    )
    benchmark._cleanup_cache_keys(local_cache, "local", ["k1", "k2"])
    assert file_a.exists() is False

    deleted = []

    class FakeRedis:
        def delete(self, *keys):
            deleted.extend(keys)

    redis_cache = SimpleNamespace(
        _redis_client=lambda: FakeRedis(),
        _redis_key=lambda key: f"redis:{key}",
    )
    benchmark._cleanup_cache_keys(redis_cache, "redis", ["k1", "k2"])
    assert deleted == ["redis:k1", "redis:k2"]


def test_run_cache_single_returns_error_when_prefill_not_visible(monkeypatch) -> None:
    cache_module = SimpleNamespace(
        CACHE_BACKEND="local",
        set=lambda key, value: None,
        get=lambda key: None,
    )
    monkeypatch.setattr(benchmark.importlib, "import_module", lambda name: cache_module)
    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = argparse.Namespace(
        backend="local",
        local_cache_dir="./benchmark",
        seed=42,
        keys=1,
        bars=2,
        read_passes=1,
        mixed_passes=1,
        cleanup=False,
    )

    assert benchmark._run_cache_single(args) == 1
    assert any("First key is missing" in line for line in printed)


def test_run_cache_single_success_with_cleanup(monkeypatch) -> None:
    store = {}
    cleanup_calls = []

    cache_module = SimpleNamespace(
        CACHE_BACKEND="local",
        set=lambda key, value: store.__setitem__(key, value.copy() if isinstance(value, dict) else value),
        get=lambda key: store.get(key),
    )
    monkeypatch.setattr(benchmark.importlib, "import_module", lambda name: cache_module)
    monkeypatch.setattr(benchmark, "_cleanup_cache_keys", lambda cache_mod, backend, keys: cleanup_calls.append((backend, list(keys))))
    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = argparse.Namespace(
        backend="local",
        local_cache_dir="./benchmark",
        seed=42,
        keys=2,
        bars=2,
        read_passes=1,
        mixed_passes=1,
        cleanup=True,
    )

    assert benchmark._run_cache_single(args) == 0
    assert cleanup_calls == [("local", ["bench:stock:TK0000", "bench:stock:TK0001"])]
    assert any("Cache Benchmark" in line for line in printed)


def test_run_cache_single_returns_error_on_warm_read_miss(monkeypatch) -> None:
    store = {}

    def fake_get(key):
        if key == "bench:stock:TK0000" and "warm_seen" in store:
            return None
        val = store.get(key)
        if key == "bench:stock:TK0000":
            store["warm_seen"] = True
        return val

    cache_module = SimpleNamespace(
        CACHE_BACKEND="local",
        set=lambda key, value: store.__setitem__(key, value.copy() if isinstance(value, dict) else value),
        get=fake_get,
    )
    monkeypatch.setattr(benchmark.importlib, "import_module", lambda name: cache_module)
    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = argparse.Namespace(
        backend="local",
        local_cache_dir="./benchmark",
        seed=42,
        keys=2,
        bars=2,
        read_passes=1,
        mixed_passes=0,
        cleanup=False,
    )

    assert benchmark._run_cache_single(args) == 1
    assert any("Cache miss during warm read" in line for line in printed)


def test_run_cache_single_returns_error_on_mixed_read_miss(monkeypatch) -> None:
    store = {}
    state = {"count": 0}

    def fake_get(key):
        state["count"] += 1
        if state["count"] >= 3:
            return None
        return store.get(key)

    cache_module = SimpleNamespace(
        CACHE_BACKEND="local",
        set=lambda key, value: store.__setitem__(key, value.copy() if isinstance(value, dict) else value),
        get=fake_get,
    )
    monkeypatch.setattr(benchmark.importlib, "import_module", lambda name: cache_module)
    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = argparse.Namespace(
        backend="local",
        local_cache_dir="./benchmark",
        seed=42,
        keys=1,
        bars=2,
        read_passes=1,
        mixed_passes=1,
        cleanup=False,
    )

    assert benchmark._run_cache_single(args) == 1
    assert any("Cache miss during mixed workload" in line for line in printed)


def test_run_cache_compare_runs_each_backend(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        benchmark.subprocess,
        "run",
        lambda cmd, check=False: calls.append(cmd) or SimpleNamespace(returncode=1 if "redis" in cmd else 0),
    )
    monkeypatch.setattr(benchmark.sys, "executable", "python")
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    args = argparse.Namespace(
        compare=["local", "redis"],
        keys=2,
        bars=3,
        read_passes=1,
        mixed_passes=1,
        seed=7,
        local_cache_dir="./bench",
        cleanup=True,
    )

    assert benchmark._run_cache_compare(args) == 1
    assert len(calls) == 2
    assert calls[0][0:3] == ["python", "-m", "app.benchmark"]
    assert "--cleanup" in calls[0]


def test_run_cache_compare_uses_default_backends_without_cleanup(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        benchmark.subprocess,
        "run",
        lambda cmd, check=False: calls.append(cmd) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(benchmark.sys, "executable", "python")
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    args = argparse.Namespace(
        compare=None,
        keys=1,
        bars=1,
        read_passes=1,
        mixed_passes=1,
        seed=1,
        local_cache_dir="./bench",
        cleanup=False,
    )

    assert benchmark._run_cache_compare(args) == 0
    assert len(calls) == 2
    assert "--cleanup" not in calls[0]


def test_main_dispatches_to_single_or_compare(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "_parse_args", lambda: argparse.Namespace(benchmark="cache", compare=None, child=False))
    monkeypatch.setattr(benchmark, "_run_cache_single", lambda args: 11)
    monkeypatch.setattr(benchmark, "_run_cache_compare", lambda args: 22)
    assert benchmark.main() == 11

    monkeypatch.setattr(benchmark, "_parse_args", lambda: argparse.Namespace(benchmark="cache", compare=["local"], child=False))
    assert benchmark.main() == 22

    monkeypatch.setattr(benchmark, "_parse_args", lambda: argparse.Namespace(benchmark="cache", compare=["local"], child=True))
    assert benchmark.main() == 11


def test_main_returns_one_for_unknown_benchmark(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(benchmark, "_parse_args", lambda: argparse.Namespace(benchmark="nope", compare=None, child=False))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    assert benchmark.main() == 1
    assert any("Unknown benchmark: nope" in line for line in printed)


def test_real_main_block_raises_system_exit_with_main_result(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "main", lambda: 7)

    source_lines = Path(benchmark.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 292 + textwrap.dedent("\n".join(source_lines[292:])) + "\n"
    code = compile(main_block, benchmark.__file__, "exec")
    globals_dict = dict(benchmark.__dict__)
    globals_dict["__name__"] = "__main__"

    try:
        exec(code, globals_dict, {})
        assert False, "Expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 7
