from contextlib import contextmanager

from app import demo_events


def test_get_demo_events_maps_rows_and_defaults(monkeypatch) -> None:
    class FakeConn:
        def close(self) -> None:
            self.closed = True

    class RowLike:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

    rows = [
        {
            "event_id": "evt-1",
            "event_date": "2026-01-01",
            "title": "First event",
            "summary": "Summary",
            "sentiment": "positive",
            "sentiment_reasoning": "Reason",
            "source": "Newswire",
            "url": "https://example.com/1",
        },
        RowLike(
            {
                "event_id": "",
                "event_date": "2026-01-02",
                "title": "Second event",
                "summary": None,
                "sentiment": None,
                "sentiment_reasoning": None,
                "source": None,
                "url": None,
            }
        ),
    ]

    executed = {}

    class FakeCursor:
        def execute(self, query, params) -> None:
            executed["query"] = query
            executed["params"] = params

        def fetchall(self):
            return rows

    @contextmanager
    def fake_cursor(_conn):
        yield FakeCursor()

    monkeypatch.setattr(demo_events, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(demo_events, "cursor", fake_cursor)

    events = demo_events.get_demo_events("nvda")

    assert executed["params"] == ("NVDA",)
    assert len(events) == 2
    assert events[0].id == "evt-1"
    assert events[0].summary == "Summary"
    assert events[0].sentiment == "positive"
    assert events[0].source == "Newswire"
    assert events[1].id == "2026-01-02"
    assert events[1].summary == "Second event"
    assert events[1].sentiment == "neutral"
    assert events[1].source == "News"


def test_get_demo_events_returns_empty_list_on_query_error(monkeypatch) -> None:
    class FakeConn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    conn = FakeConn()

    class FakeCursor:
        def execute(self, _query, _params) -> None:
            raise RuntimeError("db down")

    @contextmanager
    def fake_cursor(_conn):
        yield FakeCursor()

    monkeypatch.setattr(demo_events, "get_conn", lambda: conn)
    monkeypatch.setattr(demo_events, "cursor", fake_cursor)

    assert demo_events.get_demo_events("NVDA") == []
    assert conn.closed is True
