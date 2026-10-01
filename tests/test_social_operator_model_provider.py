from __future__ import annotations

import importlib
import json

import httpx
from fastapi.testclient import TestClient

from easel.ai_service import ConfiguredAIService, _safe_public_url, _system_proxy_for


def test_fake_ip_dns_is_allowed_only_through_configured_proxy(monkeypatch):
    info = (2, 1, 6, "", ("198.18.0.16", 443))
    monkeypatch.setattr("easel.ai_service.socket.getaddrinfo", lambda *_args: [info])
    monkeypatch.setattr("easel.ai_service.urllib.request.proxy_bypass", lambda _host: False)
    monkeypatch.setattr("easel.ai_service.urllib.request.getproxies", lambda: {})
    assert _safe_public_url("https://models.example/v1") is False

    monkeypatch.setattr("easel.ai_service.urllib.request.getproxies",
                        lambda: {"https": "http://127.0.0.1:1082"})
    assert _safe_public_url("https://models.example/v1") is True
    assert _safe_public_url("https://198.18.0.16/v1") is False
    monkeypatch.setattr("easel.ai_service.urllib.request.proxy_bypass", lambda _host: True)
    # If the host bypasses the proxy but DNS returns the VPN's synthetic IP,
    # route through the configured proxy instead of making a broken direct call.
    assert _safe_public_url("https://models.example/v1") is True


def test_system_proxy_is_used_unless_the_host_bypasses_it(monkeypatch):
    info = (2, 1, 6, "", ("93.184.216.34", 443))
    monkeypatch.setattr("easel.ai_service.socket.getaddrinfo", lambda *_args: [info])
    monkeypatch.setattr("easel.ai_service.urllib.request.getproxies",
                        lambda: {"https": "http://127.0.0.1:1082"})
    monkeypatch.setattr("easel.ai_service.urllib.request.proxy_bypass", lambda _host: False)
    assert _system_proxy_for("https://models.example/v1") == "http://127.0.0.1:1082"
    monkeypatch.setattr("easel.ai_service.urllib.request.proxy_bypass", lambda _host: True)
    assert _system_proxy_for("https://models.example/v1") is None


def test_vpn_fake_ip_destination_overrides_host_bypass_when_proxy_exists(monkeypatch):
    info = (2, 1, 6, "", ("198.18.0.16", 443))
    monkeypatch.setattr("easel.ai_service.socket.getaddrinfo", lambda *_args: [info])
    monkeypatch.setattr("easel.ai_service.urllib.request.getproxies",
                        lambda: {"https": "http://127.0.0.1:1082"})
    monkeypatch.setattr("easel.ai_service.urllib.request.proxy_bypass", lambda _host: True)
    assert _system_proxy_for("https://models.example/v1") == "http://127.0.0.1:1082"
    assert _safe_public_url("https://models.example/v1") is True


def test_web_child_preserves_system_proxy_when_easel_proxy_is_not_set(monkeypatch):
    from easel.cli import _proxy_env

    monkeypatch.setattr("easel.cli.urllib.request.getproxies", lambda: {
        "http": "http://127.0.0.1:1082", "https": "http://127.0.0.1:1082",
    })
    monkeypatch.delenv("EASEL_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    env = _proxy_env()
    assert env["http_proxy"] == "http://127.0.0.1:1082"
    assert env["https_proxy"] == "http://127.0.0.1:1082"


def test_selected_custom_provider_is_used_by_ai_service_without_gateway(monkeypatch):
    runtime = ConfiguredAIService(env={
        "EASEL_AI_PROVIDER_NAME": "qwen-cloud",
        "EASEL_AI_BASE_URL": "https://models.example/v1",
        "EASEL_AI_API_KEY": "test-key-not-real",
        "EASEL_AI_MODEL": "qwen-plus",
    })
    monkeypatch.setattr("easel.ai_service._safe_public_url", lambda _url: True)
    monkeypatch.setattr(runtime, "_gateway_configured", lambda: False)
    monkeypatch.setattr(runtime, "_gateway_probe", lambda: False)
    captured = {}

    def post(url, *, headers, json, **_kwargs):
        captured.update(url=url, headers=headers, body=json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr("easel.ai_service.httpx.post", post)
    assert runtime.complete("system", "user") == "OK"
    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["body"]["model"] == "qwen-plus"
    assert captured["headers"]["authorization"] == "Bearer test-key-not-real"
    assert runtime.providers[0].label == "qwen-cloud"


def test_custom_provider_settings_save_to_env_and_return_only_masked_key(tmp_path, monkeypatch):
    web_app = importlib.import_module("web.app")
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_app, "ENV_FILE", env_path)
    monkeypatch.setattr(web_app, "_sync_openclaw_chat", lambda *_args: "")
    local = "http://localhost:7860"
    client = TestClient(web_app.app, base_url=local, client=("127.0.0.1", 51237), headers={"Origin": local})

    response = client.post("/api/settings/models/save", json={
        "channel": "chat",
        "rows": [{
            "slot": "custom", "name": "qwen-cloud", "model": "qwen-plus",
            "baseUrl": "https://models.example/v1", "key": "test-key-not-real", "primary": True,
        }],
    })
    assert response.status_code == 200
    assert "test-key-not-real" not in response.text
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines() if "=" in line)
    assert values["EASEL_AI_PROVIDER_NAME"] == "qwen-cloud"
    assert values["EASEL_AI_BASE_URL"] == "https://models.example/v1"
    assert values["EASEL_AI_MODEL"] == "qwen-plus"
    assert values["EASEL_AI_API_KEY"] == "test-key-not-real"
    row = next(row for row in response.json()["channels"]["chat"]["rows"] if row["name"] == "qwen-cloud")
    assert row["keyMasked"] != "test-key-not-real"
    assert row["model"] == "qwen-plus"


def test_first_custom_provider_is_saved_when_ui_has_no_primary_row(tmp_path, monkeypatch):
    web_app = importlib.import_module("web.app")
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_app, "ENV_FILE", env_path)
    monkeypatch.setattr(web_app, "_sync_openclaw_chat", lambda *_args: "")
    local = "http://localhost:7860"
    client = TestClient(web_app.app, base_url=local, client=("127.0.0.1", 51237), headers={"Origin": local})
    response = client.post("/api/settings/models/save", json={
        "channel": "chat",
        "rows": [{
            "slot": "custom", "name": "deepseek", "model": "deepseek-chat",
            "baseUrl": "https://models.example/v1", "key": "test-key-not-real", "primary": False,
        }],
    })
    assert response.status_code == 200
    assert any(row["name"] == "deepseek" for row in response.json()["channels"]["chat"]["rows"])
    assert "EASEL_AI_API_KEY=test-key-not-real" in env_path.read_text()


def test_chat_selftest_checks_the_configured_completion_model_without_echoing_key(monkeypatch):
    web_app = importlib.import_module("web.app")
    monkeypatch.setattr(web_app, "_read_env", lambda: {
        "EASEL_AI_PROVIDER_NAME": "qwen-cloud",
        "EASEL_AI_BASE_URL": "https://models.example/v1",
        "EASEL_AI_API_KEY": "test-key-not-real",
        "EASEL_AI_MODEL": "qwen-plus",
    })
    monkeypatch.setattr(web_app, "_ssrf_safe", lambda _url: True)
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, request, timeout):
            captured["method"] = request.get_method()
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data)
            return Response()

    monkeypatch.setattr(web_app.urllib.request, "build_opener", lambda *_args: Opener())
    local = "http://localhost:7860"
    client = TestClient(web_app.app, base_url=local, client=("127.0.0.1", 51237), headers={"Origin": local})
    result = client.post("/api/settings/models/selftest", json={"channel": "chat"})
    assert result.status_code == 200
    assert result.json()["results"][0]["ok"] is True
    assert captured["method"] == "POST"
    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["body"]["model"] == "qwen-plus"
    assert captured["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert "test-key-not-real" not in result.text
