from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx

from app.learning.resources import refresh_knowledge_sources


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Db:
    def __init__(self, sources):
        self.sources = sources

    def scalars(self, _statement):
        return _ScalarResult(self.sources)


class _Checker:
    def __init__(self, head_status=200, get_status=200):
        self.head_status = head_status
        self.get_status = get_status
        self.calls = []

    def _response(self, method, url, status):
        return httpx.Response(status, request=httpx.Request(method, url))

    def head(self, url):
        self.calls.append(("HEAD", url))
        return self._response("HEAD", url, self.head_status)

    def get(self, url):
        self.calls.append(("GET", url))
        return self._response("GET", url, self.get_status)


def _source(*, verified_at, status="unverified"):
    return SimpleNamespace(
        canonical_url="https://developer.mozilla.org/example",
        verified_at=verified_at,
        last_checked_at=None,
        freshness_status=status,
        last_check_status=None,
        last_check_error=None,
    )


def test_refresh_marks_successful_official_source_current():
    now = datetime(2026, 8, 30, tzinfo=UTC)
    source = _source(verified_at=now - timedelta(days=60))
    checker = _Checker()

    summary = refresh_knowledge_sources(_Db([source]), checker=checker, now=now)

    assert summary == {"checked": 1, "verified": 1, "unavailable": 0, "skipped_fresh": 0}
    assert source.verified_at == now
    assert source.last_checked_at == now
    assert source.freshness_status == "current"
    assert source.last_check_status == 200
    assert source.last_check_error is None


def test_refresh_retains_last_verified_time_when_source_is_unavailable():
    now = datetime(2026, 8, 30, tzinfo=UTC)
    previous = now - timedelta(days=45)
    source = _source(verified_at=previous)

    summary = refresh_knowledge_sources(
        _Db([source]), checker=_Checker(head_status=503), now=now
    )

    assert summary["unavailable"] == 1
    assert source.verified_at == previous
    assert source.last_checked_at == now
    assert source.freshness_status == "unavailable"
    assert source.last_check_status == 503
    assert source.last_check_error == "HTTPStatusError"


def test_refresh_skips_recent_source_and_falls_back_to_get_when_head_is_blocked():
    now = datetime(2026, 8, 30, tzinfo=UTC)
    current = _source(verified_at=now - timedelta(days=2), status="current")
    stale = _source(verified_at=now - timedelta(days=45))
    checker = _Checker(head_status=405, get_status=200)

    summary = refresh_knowledge_sources(_Db([current, stale]), checker=checker, now=now)

    assert summary == {"checked": 1, "verified": 1, "unavailable": 0, "skipped_fresh": 1}
    assert checker.calls == [
        ("HEAD", stale.canonical_url),
        ("GET", stale.canonical_url),
    ]