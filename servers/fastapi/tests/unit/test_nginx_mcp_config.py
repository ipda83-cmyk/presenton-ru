import re
from pathlib import Path


NGINX_CONFIG = Path(__file__).resolve().parents[4] / "nginx.conf"


def _location_block(config: str, path: str) -> str:
    match = re.search(
        rf"location {re.escape(path)} \{{(?P<body>.*?)\n    \}}",
        config,
        flags=re.DOTALL,
    )
    assert match is not None, f"Missing Nginx location for {path}"
    return match.group("body")


def test_mcp_routes_delegate_authentication_to_fastmcp():
    config = NGINX_CONFIG.read_text(encoding="utf-8")

    for path in ("/mcp/", "/mcp"):
        block = _location_block(config, path)
        assert "auth_request" not in block
        assert "proxy_pass http://127.0.0.1:8001/mcp" in block
        assert "proxy_set_header Host localhost:8001;" in block


def test_private_app_data_routes_still_use_auth_subrequest():
    config = NGINX_CONFIG.read_text(encoding="utf-8")

    for path in (
        "/app_data/images/",
        "/app_data/exports/",
        "/app_data/uploads/",
    ):
        assert "auth_request /_auth_check;" in _location_block(config, path)


def test_upstreams_use_the_loopback_address_not_localhost():
    # The servers listen on 127.0.0.1 only, while "localhost" also resolves to ::1.
    # nginx then keeps two peers per worker; requests made while FastAPI starts mark
    # both down, and later bursts got "502 no live upstreams" until a probe passed.
    config = NGINX_CONFIG.read_text(encoding="utf-8")
    assert re.findall(r"proxy_pass http://localhost", config) == []
    assert "proxy_pass http://127.0.0.1:8000;" in _location_block(config, "/api/v1/")
