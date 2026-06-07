from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_accepts_configured_upload_size_and_overwrites_forwarded_ip():
    config = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "client_max_body_size 55m;" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert "$proxy_add_x_forwarded_for" not in config


def test_compose_uses_worker_entrypoint_and_loopback_ports():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "command: python -m app.rq_worker" in compose
    assert "TRUST_PROXY_HEADERS=true" in compose
    assert compose.count('127.0.0.1:') >= 5
