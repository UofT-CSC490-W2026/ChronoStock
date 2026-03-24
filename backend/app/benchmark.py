"""
Unified benchmark entrypoint.

Usage examples:
  # Run cache benchmark (default benchmark)
  python -m app.benchmark cache

  # Compare local and redis cache backends
  python -m app.benchmark cache --compare local redis
"""
from __future__ import annotations

import argparse
import importlib
import os
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChronoStock benchmark runner")
    parser.add_argument(
        "benchmark",
        nargs="?",
        default="cache",
        choices=["cache"],
        help="Benchmark to run.",
    )

    # Cache benchmark options
    parser.add_argument(
        "--compare",
        nargs="*",
        choices=["local", "redis"],
        help="Run child benchmarks for each backend listed.",
    )

    parser.add_argument(
        "--backend",
        choices=["local", "redis", "s3"],
        default=None,
        help="Override CACHE_BACKEND for this process.",
    )

    parser.add_argument("--keys", type=int, default=120, help="Number of unique cache keys.")
    parser.add_argument("--bars", type=int, default=900, help="Bars per payload (controls payload size).")
    parser.add_argument("--read-passes", type=int, default=18, help="Warm read passes over all keys.")
    parser.add_argument("--mixed-passes", type=int, default=6, help="Mixed read/write passes over all keys.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic generation/order.")
    parser.add_argument(
        "--local-cache-dir",
        default="./benchmark",
        help="Cache dir used when backend is local.",
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete benchmark keys/files at the end.",
    )

    parser.add_argument(
        "--child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    
    return parser.parse_args()


def _build_keys(num_keys: int) -> list[str]:
    return [f"bench:stock:TK{i:04d}" for i in range(num_keys)]


def _build_payload(ticker: str, bars_count: int, rng: random.Random) -> dict[str, Any]:
    base = rng.uniform(50.0, 350.0)
    bars: list[dict[str, Any]] = []
    day0 = datetime(2018, 1, 1, tzinfo=timezone.utc)

    for i in range(bars_count):
        d = (day0 + timedelta(days=i)).strftime("%Y-%m-%d")
        drift = i * 0.03
        noise = rng.uniform(-1.0, 1.0)
        close = round(base + drift + noise, 2)
        open_ = round(close + rng.uniform(-0.8, 0.8), 2)
        high = round(max(open_, close) + rng.uniform(0.0, 1.4), 2)
        low = round(min(open_, close) - rng.uniform(0.0, 1.2), 2)
        volume = int(1_000_000 + i * 120 + rng.randint(0, 15000))
        bars.append(
            {
                "time": d,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    return {
        "ticker": ticker,
        "companyName": f"{ticker} Corp",
        "bars": bars,
        "events": [],
        "meta": {"marketCap": 1_000_000_000.0, "beta": 1.1},
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = int(round((len(sorted_values) - 1) * pct))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def _stats(samples_ms: list[float]) -> dict[str, float]:
    vals = sorted(samples_ms)
    return {
        "count": float(len(vals)),
        "mean_ms": statistics.fmean(vals) if vals else 0.0,
        "50th_percentile_ms": _percentile(vals, 0.50),
        "95th_percentile_ms": _percentile(vals, 0.95),
        "99th_percentile_ms": _percentile(vals, 0.99),
    }


def _format_stats(name: str, samples_ms: list[float]) -> str:
    s = _stats(samples_ms)
    count = int(s["count"])
    return (
        f"{name:<14} count={count:<6} "
        f"mean={s['mean_ms']:.3f}ms "
        f"50th_percentile={s['50th_percentile_ms']:.3f}ms "
        f"95th_percentile={s['95th_percentile_ms']:.3f}ms "
        f"99th_percentile={s['99th_percentile_ms']:.3f}ms"
    )


def _cleanup_cache_keys(cache_module: Any, backend: str, keys: list[str]) -> None:
    if backend == "local":
        base: Path = cache_module.LOCAL_CACHE_DIR
        for key in keys:
            path = base / cache_module._filename(key)
            if path.exists():
                path.unlink()
        return

    if backend == "redis":
        client = cache_module._redis_client()
        redis_keys = [cache_module._redis_key(k) for k in keys]
        if redis_keys:
            client.delete(*redis_keys)


def _run_cache_single(args: argparse.Namespace) -> int:
    if args.backend:
        os.environ["CACHE_BACKEND"] = args.backend
    os.environ["LOCAL_CACHE_DIR"] = args.local_cache_dir

    cache_module = importlib.import_module("app.cache")
    backend = cache_module.CACHE_BACKEND

    rng = random.Random(args.seed)
    keys = _build_keys(args.keys)
    payloads = {k: _build_payload(k.split(":")[-1], args.bars, rng) for k in keys}

    set_ms: list[float] = []
    get_ms: list[float] = []
    mixed_get_ms: list[float] = []
    mixed_set_ms: list[float] = []

    # Phase 1: prefill (deterministic writes)
    t0 = time.perf_counter()
    for key in keys:
        op0 = time.perf_counter()
        cache_module.set(key, payloads[key])
        set_ms.append((time.perf_counter() - op0) * 1000.0)
    prefill_total_s = time.perf_counter() - t0

    # Ensure writes are visible before measuring reads.
    first_read = cache_module.get(keys[0])
    if first_read is None:
        print(
            f"[ERROR] First key is missing after prefill using backend='{backend}'. "
            "Check backend availability/config."
        )
        return 1

    # Phase 2: warm read workload with deterministic key order per pass.
    t1 = time.perf_counter()
    for p in range(args.read_passes):
        shuffled = list(keys)
        random.Random(args.seed + p).shuffle(shuffled)
        for key in shuffled:
            op0 = time.perf_counter()
            val = cache_module.get(key)
            get_ms.append((time.perf_counter() - op0) * 1000.0)
            if val is None:
                print(f"[ERROR] Cache miss during warm read: {key}")
                return 1
    reads_total_s = time.perf_counter() - t1

    # Phase 3: mixed workload (1 get + 1 set per key per pass).
    t2 = time.perf_counter()
    for p in range(args.mixed_passes):
        shuffled = list(keys)
        random.Random(args.seed + 1000 + p).shuffle(shuffled)
        for i, key in enumerate(shuffled):
            op0 = time.perf_counter()
            val = cache_module.get(key)
            mixed_get_ms.append((time.perf_counter() - op0) * 1000.0)
            if val is None:
                print(f"[ERROR] Cache miss during mixed workload: {key}")
                return 1

            # Deterministic small mutation to keep write path active.
            val["cached_at"] = datetime.now(timezone.utc).isoformat()
            val["meta"]["touch"] = f"{p}-{i}"
            op1 = time.perf_counter()
            cache_module.set(key, val)
            mixed_set_ms.append((time.perf_counter() - op1) * 1000.0)
    mixed_total_s = time.perf_counter() - t2

    if args.cleanup:
        _cleanup_cache_keys(cache_module, backend, keys)

    print("======================================== Cache Benchmark =================================================")
    print(f"backend={backend} keys={args.keys} bars={args.bars} seed={args.seed}")
    print(f"local_cache_dir={os.environ.get('LOCAL_CACHE_DIR')}")
    print(f"prefill_total={prefill_total_s:.3f}s reads_total={reads_total_s:.3f}s mixed_total={mixed_total_s:.3f}s")
    print(_format_stats("set_prefill", set_ms))
    print(_format_stats("get_warm", get_ms))
    print(_format_stats("get_mixed", mixed_get_ms))
    print(_format_stats("set_mixed", mixed_set_ms))
    return 0


def _run_cache_compare(args: argparse.Namespace) -> int:
    backends = args.compare or ["local", "redis"]
    ret = 0
    for backend in backends:
        cmd = [
            sys.executable,
            "-m",
            "app.benchmark",
            "cache",
            "--backend",
            backend,
            "--keys",
            str(args.keys),
            "--bars",
            str(args.bars),
            "--read-passes",
            str(args.read_passes),
            "--mixed-passes",
            str(args.mixed_passes),
            "--seed",
            str(args.seed),
            "--local-cache-dir",
            args.local_cache_dir,
            "--child",
        ]
        if args.cleanup:
            cmd.append("--cleanup")

        print(f"\nRunning CACHE_BACKEND={backend}")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            ret = completed.returncode
    return ret


def main() -> int:
    args = _parse_args()

    if args.benchmark == "cache":
        if args.compare and not args.child:
            return _run_cache_compare(args)
        return _run_cache_single(args)

    print(f"Unknown benchmark: {args.benchmark}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
