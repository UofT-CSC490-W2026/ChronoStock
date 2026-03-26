import builtins
from pathlib import Path
import textwrap

from app.pipelines import run_hourly_update


def test_main_refreshes_prices_and_prints(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(run_hourly_update, "build_update_tickers", lambda: ["NVDA", "AAPL"])
    monkeypatch.setattr(run_hourly_update, "refresh_prices", lambda tickers: calls.append(tickers))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    run_hourly_update.main()

    assert calls == [["NVDA", "AAPL"]]
    assert any("Hourly update complete for 2 ticker(s)." in line for line in printed)


def test_real_main_block_executes_file_lines(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(run_hourly_update, "build_update_tickers", lambda: ["NVDA"])
    monkeypatch.setattr(run_hourly_update, "refresh_prices", lambda tickers: calls.append(tickers))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    source_lines = Path(run_hourly_update.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 7 + textwrap.dedent("\n".join(source_lines[7:])) + "\n"
    code = compile(main_block, run_hourly_update.__file__, "exec")
    globals_dict = dict(run_hourly_update.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == [["NVDA"]]
    assert any("Hourly update complete for 1 ticker(s)." in line for line in printed)
