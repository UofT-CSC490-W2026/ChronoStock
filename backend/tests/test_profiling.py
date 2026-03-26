import builtins
from pathlib import Path
import textwrap
from types import SimpleNamespace

from app import profiling


def test_main_profiles_server_and_writes_report(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "report.txt"
    calls = {"uvicorn": None, "print_stats": None}

    class FakeProfile:
        def runcall(self, func, *args, **kwargs):
            calls["uvicorn"] = (func, args, kwargs)

    class FakeStats:
        def __init__(self, profiler, stream):
            self.stream = stream

        def sort_stats(self, key):
            assert key == "cumulative"
            return self

        def print_stats(self, path, limit):
            calls["print_stats"] = (path, limit)
            self.stream.write("report")

    printed = []
    monkeypatch.setattr(profiling, "REPORT_PATH", str(report_path))
    monkeypatch.setattr(profiling.cProfile, "Profile", lambda: FakeProfile())
    monkeypatch.setattr(profiling.pstats, "Stats", FakeStats)
    monkeypatch.setattr(profiling.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    profiling.main()

    assert calls["uvicorn"][0] == profiling.uvicorn.run
    assert calls["print_stats"][1] == profiling.NUM_REPORT
    assert calls["print_stats"][0].endswith("app")
    assert report_path.read_text(encoding="utf-8") == "report"
    assert any("Report saved to" in line for line in printed)


def test_real_main_block_invokes_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(profiling, "main", lambda: calls.append("main"))

    source_lines = Path(profiling.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 22 + textwrap.dedent("\n".join(source_lines[22:])) + "\n"
    code = compile(main_block, profiling.__file__, "exec")
    globals_dict = dict(profiling.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
