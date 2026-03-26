from app import edgar


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_get_cik_uses_cached_mapping(monkeypatch) -> None:
    monkeypatch.setattr(edgar.cache, "get", lambda key: {"data": {"NVDA": 1045810}})

    called = {"count": 0}

    def fail_http(*_args, **_kwargs):
        called["count"] += 1
        raise AssertionError("httpx.get should not be called")

    monkeypatch.setattr(edgar.httpx, "get", fail_http)

    assert edgar._get_cik("nvda") == "0001045810"
    assert called["count"] == 0


def test_get_cik_fetches_and_caches_mapping_on_miss(monkeypatch) -> None:
    cache_sets = []
    monkeypatch.setattr(edgar.cache, "get", lambda key: None)
    monkeypatch.setattr(edgar.cache, "set", lambda key, value: cache_sets.append((key, value)))
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda url, headers, timeout: FakeResponse(
            {
                "0": {"ticker": "NVDA", "cik_str": 1045810},
                "1": {"ticker": "AAPL", "cik_str": 320193},
            }
        ),
    )

    assert edgar._get_cik("NVDA") == "0001045810"
    assert cache_sets == [("sec:cik_map", {"data": {"NVDA": 1045810, "AAPL": 320193}})]


def test_get_cik_returns_none_when_ticker_not_found(monkeypatch) -> None:
    monkeypatch.setattr(edgar.cache, "get", lambda key: {"data": {"AAPL": 320193}})
    assert edgar._get_cik("NVDA") is None


def test_get_cik_returns_none_when_remote_mapping_lacks_ticker(monkeypatch) -> None:
    monkeypatch.setattr(edgar.cache, "get", lambda key: None)
    monkeypatch.setattr(edgar.cache, "set", lambda key, value: None)
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda url, headers, timeout: FakeResponse(
            {
                "0": {"ticker": "AAPL", "cik_str": 320193},
            }
        ),
    )

    assert edgar._get_cik("NVDA") is None


def test_fetch_sec_filings_filters_forms_and_builds_labels(monkeypatch) -> None:
    monkeypatch.setattr(edgar, "_get_cik", lambda ticker: "0001045810")
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda url, headers, timeout: FakeResponse(
            {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001-01", "0002-02", "0003-03"],
                        "filingDate": ["2026-01-03", "2026-01-02", "2026-01-01"],
                        "form": ["8-K", "4", "10-Q"],
                        "primaryDocument": ["eightk.htm", "form4.htm", "tenq.htm"],
                        "items": ["2.02,5.02", "", ""],
                    }
                }
            }
        ),
    )

    filings = edgar.fetch_sec_filings("NVDA")

    assert len(filings) == 2
    assert filings[0].date == "2026-01-03"
    assert filings[0].form == "8-K"
    assert filings[0].items == ["2.02", "5.02"]
    assert "Earnings Release" in filings[0].label
    assert "Leadership Change" in filings[0].label
    assert filings[0].url.endswith("/000101/eightk.htm")
    assert filings[1].form == "4"
    assert filings[1].label == "Insider Transaction"
    assert filings[1].items == []


def test_fetch_sec_filings_returns_empty_when_cik_missing(monkeypatch) -> None:
    monkeypatch.setattr(edgar, "_get_cik", lambda ticker: None)

    called = {"count": 0}

    def fail_http(*_args, **_kwargs):
        called["count"] += 1
        raise AssertionError("httpx.get should not be called")

    monkeypatch.setattr(edgar.httpx, "get", fail_http)

    assert edgar.fetch_sec_filings("NVDA") == []
    assert called["count"] == 0
