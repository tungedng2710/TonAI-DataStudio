from pathlib import Path


def test_web_proxy_resolves_recreated_api_containers_dynamically() -> None:
    config = Path("apps/web/nginx.conf").read_text()

    assert "resolver 127.0.0.11" in config
    assert "set $api_upstream api:8000;" in config
    assert "proxy_pass http://$api_upstream" in config
    assert "proxy_pass http://api:8000" not in config
