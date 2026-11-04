import datetime as dt
import io
import json
import urllib.error

import pytest

from scripts import download_data as dd


def test_day_window_follows_canberra_daylight_saving():
    # Winter (AEST, +10): midnight is 14:00 UTC the day before.
    assert dd.day_window_utc(dt.date(2024, 7, 1)) == ("2024-06-30T14:00:00Z", "2024-07-01T14:00:00Z")
    # Summer (AEDT, +11): midnight is 13:00 UTC.
    assert dd.day_window_utc(dt.date(2025, 1, 15)) == ("2025-01-14T13:00:00Z", "2025-01-15T13:00:00Z")
    # Daylight saving starts on 6 Oct 2024: that day is 23 hours long.
    assert dd.day_window_utc(dt.date(2024, 10, 6)) == ("2024-10-05T14:00:00Z", "2024-10-06T13:00:00Z")


def page(releases, nxt=None, licence=dd.EXPECTED_LICENCE):
    return {"license": licence, "releases": releases, "links": {"next": nxt} if nxt else {}}


def test_fetch_day_follows_the_cursor_until_it_ends(monkeypatch):
    pages = {
        "first": page([{"id": "a"}, {"id": "b"}], nxt="second"),
        "second": page([{"id": "c"}], nxt="third"),
        "third": page([]),
    }
    monkeypatch.setattr(dd, "API", "{start}{end}")
    first_url = "".join(dd.day_window_utc(dt.date(2024, 7, 1)))
    monkeypatch.setattr(dd, "get_json", lambda url: pages["first" if url == first_url else url])
    out = dd.fetch_day(dt.date(2024, 7, 1), pause=0)
    assert [r["id"] for r in out["releases"]] == ["a", "b", "c"]
    assert out["pages"] == 3


def test_fetch_day_stops_on_a_cursor_loop(monkeypatch):
    monkeypatch.setattr(dd, "get_json", lambda url: page([{"id": url}], nxt="loop"))
    out = dd.fetch_day(dt.date(2024, 7, 1), pause=0)
    assert len(out["releases"]) == 2  # the first page, then "loop" once


def test_fetch_day_refuses_a_changed_licence(monkeypatch):
    monkeypatch.setattr(dd, "get_json", lambda url: page([{"id": "a"}], licence="other"))
    with pytest.raises(RuntimeError, match="licence"):
        dd.fetch_day(dt.date(2024, 7, 1), pause=0)


def _http_400(body: str):
    return urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(body.encode()))


def test_no_records_answer_is_an_empty_day(monkeypatch):
    def raise_no_records(req, timeout):
        raise _http_400(json.dumps({"errorCode": 100, "message": "No Records found"}))

    monkeypatch.setattr(dd.urllib.request, "urlopen", raise_no_records)
    out = dd.fetch_day(dt.date(2024, 7, 7), pause=0)
    assert out["releases"] == [] and out["pages"] == 1


def test_other_client_errors_are_raised_without_retrying(monkeypatch):
    calls = []

    def bad_request(req, timeout):
        calls.append(1)
        raise _http_400(json.dumps({"errorCode": 7, "message": "bad date"}))

    monkeypatch.setattr(dd.urllib.request, "urlopen", bad_request)
    with pytest.raises(urllib.error.HTTPError):
        dd.get_json("https://example.invalid/x")
    assert len(calls) == 1


def test_no_records_after_some_pages_is_an_error(monkeypatch):
    def fake(url):
        if url.endswith("Z"):
            return page([{"id": "a"}], nxt="next")
        raise dd.NoRecords("gone")

    monkeypatch.setattr(dd, "get_json", fake)
    with pytest.raises(dd.NoRecords):
        dd.fetch_day(dt.date(2024, 7, 1), pause=0)


def test_save_day_writes_atomically(tmp_path):
    out = dd.save_day({"day": "2024-07-01", "releases": []}, raw_dir=tmp_path)
    assert out.name == "2024-07-01.json.gz"
    assert not list(tmp_path.glob("*.part"))
