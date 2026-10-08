import asyncio

from utils import web_search
from utils.web_search import WebSearchResult


class _Response:
    def __init__(self, status, location=None):
        self.status = status
        self.headers = {"Location": location} if location else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    """Answers by URL; a callable answer may raise (timeouts, refused)."""

    def __init__(self, answers):
        self.answers = answers
        self.requested = []

    def get(self, url, allow_redirects):
        assert allow_redirects is False
        self.requested.append(url)
        answer = self.answers[url]
        if callable(answer):
            answer()
        return answer


def _resolver(public_hosts, internal_hosts=(), no_dns=()):
    async def resolve(host):
        if host in no_dns:
            return None
        if host in internal_hosts:
            return False
        assert host in public_hosts, host
        return True

    return resolve


def test_link_status_follows_redirects_and_refuses_internal_targets(monkeypatch):
    monkeypatch.setattr(
        web_search,
        "_resolves_to_public_addresses",
        _resolver(
            {"ok.example", "gone.example", "moved.example", "evil.example", "slow.example"},
            internal_hosts={"10.0.0.1", "intranet.example"},
            no_dns={"nodns.example"},
        ),
    )

    def time_out():
        raise asyncio.TimeoutError

    session = _Session(
        {
            "https://ok.example/": _Response(200),
            "https://gone.example/": _Response(404),
            "https://moved.example/": _Response(301, "/page"),
            "https://moved.example/page": _Response(200),
            "https://evil.example/": _Response(302, "http://10.0.0.1/admin"),
            "https://slow.example/": time_out,
        }
    )

    async def statuses():
        return [
            await web_search._link_status(session, url)
            for url in (
                "https://ok.example/",
                "https://gone.example/",
                "https://moved.example/",
                "https://evil.example/",
                "http://intranet.example/",
                "https://nodns.example/",
                "https://slow.example/",
                "ftp://ok.example/",
            )
        ]

    assert asyncio.run(statuses()) == [
        "ok",
        "broken",
        "ok",
        "broken",
        "broken",
        "unknown",
        "unknown",
        "broken",
    ]
    # Internal addresses are never requested, not even after a redirect.
    assert "http://10.0.0.1/admin" not in session.requested
    assert "http://intranet.example/" not in session.requested


def test_drop_broken_links_keeps_facts_and_uncertain_links(monkeypatch):
    async def fake_status(_session, url):
        return {"https://gone.example/": "broken", "https://slow.example/": "unknown"}.get(
            url, "ok"
        )

    monkeypatch.setattr(web_search, "_link_status", fake_status)
    results = [
        WebSearchResult("Web search summary", "", "Facts."),
        WebSearchResult("Ok", "https://ok.example/", "a"),
        WebSearchResult("Gone", "https://gone.example/", "b"),
        WebSearchResult("Slow", "https://slow.example/", "c"),
    ]

    kept = asyncio.run(web_search._drop_broken_links(results))

    assert [result.url for result in kept] == ["", "https://ok.example/", "https://slow.example/"]


def test_gateway_trims_to_the_limit_after_dropping_broken_links(monkeypatch):
    links = "\n".join(f"- [Page {i}](https://site{i}.example/): text {i}" for i in range(6))
    payload = {"choices": [{"message": {"content": f"Facts.\nSOURCES:\n{links}"}}]}

    class _GatewayResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def json(self, content_type=None):
            return payload

    class _GatewaySession:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return _GatewayResponse()

    async def drop_first_two(results):
        return [r for r in results if r.url not in ("https://site0.example/", "https://site1.example/")]

    monkeypatch.setattr(web_search.aiohttp, "ClientSession", _GatewaySession)
    monkeypatch.setattr(web_search, "_drop_broken_links", drop_first_two)

    results = asyncio.run(
        web_search._search_chat_gateway("https://gw.example/api/v1", "key", "model", "q", 3)
    )

    assert [result.url for result in results] == [
        "",
        "https://site2.example/",
        "https://site3.example/",
        "https://site4.example/",
    ]


def test_ip_literals_are_classified_without_network():
    async def classify():
        return (
            await web_search._resolves_to_public_addresses("127.0.0.1"),
            await web_search._resolves_to_public_addresses("10.1.2.3"),
            await web_search._resolves_to_public_addresses("169.254.169.254"),
            await web_search._resolves_to_public_addresses("8.8.8.8"),
        )

    assert asyncio.run(classify()) == (False, False, False, True)
