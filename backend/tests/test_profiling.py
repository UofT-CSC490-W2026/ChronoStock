import builtins
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace

import pytest

from app import profiling


def test_get_auth_header_returns_empty_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_EMAIL", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)

    assert profiling._get_auth_header(SimpleNamespace()) == {}


def test_main_profiles_server_and_writes_report(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "report.txt"
    calls = {"print_stats": None, "requests": []}

    class FakeProfile:
        def enable(self):
            calls["enabled"] = True

        def disable(self):
            calls["disabled"] = True

    class FakeStats:
        def __init__(self, profiler, stream):
            self.stream = stream

        def sort_stats(self, key):
            assert key == "cumulative"
            return self

        def print_stats(self, path, limit):
            calls["print_stats"] = (path, limit)
            self.stream.write("report")

    class FakeClient:
        def __init__(self, app, raise_server_exceptions=True):
            calls["client_init"] = (app, raise_server_exceptions)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path, json=None, headers=None):
            if path == "/auth/login":
                calls["login"] = (path, json)
                return SimpleNamespace(status_code=200, json=lambda: {"access_token": "abc"})
            calls["requests"].append((path, headers))
            return SimpleNamespace(status_code=200, json=lambda: {})

        def get(self, path, headers=None):
            calls["requests"].append((path, headers))
            return SimpleNamespace(status_code=200, json=lambda: {})

        def delete(self, path, headers=None):
            calls["requests"].append((path, headers))
            return SimpleNamespace(status_code=200, json=lambda: {})

    printed = []
    monkeypatch.setattr(profiling, "REPORT_PATH", str(report_path))
    monkeypatch.setattr(profiling.cProfile, "Profile", lambda: FakeProfile())
    monkeypatch.setattr(profiling.pstats, "Stats", FakeStats)
    monkeypatch.setenv("AUTH_EMAIL", "user@example.com")
    monkeypatch.setenv("AUTH_PASSWORD", "secret")
    monkeypatch.setattr(sys, "argv", ["profiling.py", "--ticker", "msft", "--indicator", "CPI"])
    monkeypatch.setitem(sys.modules, "fastapi.testclient", SimpleNamespace(TestClient=FakeClient))
    monkeypatch.setitem(sys.modules, "app.main", SimpleNamespace(app="fake-app"))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    profiling.main()

    assert calls["print_stats"][1] == profiling.NUM_REPORT
    assert calls["print_stats"][0].endswith("app")
    assert calls["client_init"] == ("fake-app", True)
    assert calls["login"] == ("/auth/login", {"email": "user@example.com", "password": "secret"})
    assert calls["requests"][0] == ("/health", None)
    assert calls["requests"][-1] == ("/api/search?q=MSFT", None)
    assert report_path.read_text(encoding="utf-8") == "report"
    assert any("Report saved to" in line for line in printed)


def test_main_raises_when_authentication_fails(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, app, raise_server_exceptions=True):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path, json=None, headers=None):
            return SimpleNamespace(status_code=401, json=lambda: {})

    monkeypatch.setenv("AUTH_EMAIL", "user@example.com")
    monkeypatch.setenv("AUTH_PASSWORD", "secret")
    monkeypatch.setattr(sys, "argv", ["profiling.py"])
    monkeypatch.setitem(sys.modules, "fastapi.testclient", SimpleNamespace(TestClient=FakeClient))
    monkeypatch.setitem(sys.modules, "app.main", SimpleNamespace(app="fake-app"))

    with pytest.raises(SystemExit, match="Authentication failed"):
        profiling.main()


def test_real_main_block_invokes_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(profiling, "main", lambda: calls.append("main"))

    source_lines = Path(profiling.__file__).read_text(encoding="utf-8").splitlines()
    main_index = next(i for i, line in enumerate(source_lines) if line.startswith('if __name__ == "__main__":'))
    main_block = "\n" * main_index + textwrap.dedent("\n".join(source_lines[main_index:])) + "\n"
    code = compile(main_block, profiling.__file__, "exec")
    globals_dict = dict(profiling.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
