"""Provider-neutral chat completion runtime shared by AI-backed features.

Provider configuration remains owned by Easel's existing ``.env`` and
OpenClaw profile. This module adapts those settings without adding an SDK.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PLACEHOLDERS = ("replace_me", "your-api-key", "your_api_key", "xxx")
_VPN_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


class AIRuntimeState(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class AIRuntimeStatus:
    state: AIRuntimeState
    provider: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"state": self.state.value, "provider": self.provider, "detail": self.detail}


class AIServiceError(RuntimeError):
    def __init__(self, state: AIRuntimeState, message: str):
        super().__init__(message)
        self.state = state


class AIService(Protocol):
    def runtime_status(self) -> AIRuntimeStatus: ...
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass(frozen=True)
class _Provider:
    kind: str
    label: str
    base_url: str
    api_key: str
    model: str
    headers: dict[str, str]

    @property
    def completion_url(self) -> str:
        if self.kind == "anthropic":
            return self.base_url.rstrip("/") + "/messages"
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def probe_url(self) -> str:
        if self.kind == "anthropic":
            return self.base_url.rstrip("/") + "/models"
        return self.base_url.rstrip("/") + "/models"


def _read_env() -> dict[str, str]:
    path = PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    for key, value in os.environ.items():
        values.setdefault(key, value)
    return values


def _configured(value: str | None) -> bool:
    value = (value or "").strip()
    return bool(value) and not any(token in value.lower() for token in _PLACEHOLDERS)


def _safe_public_url(url: str) -> bool:
    """Never send provider credentials to localhost or private network targets."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        try:
            ipaddress.ip_address(parsed.hostname)
            literal_address = True
        except ValueError:
            literal_address = False
        proxy_available = bool(_system_proxy_for(url))
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip in _VPN_FAKE_IP_NETWORK:
                if proxy_available and not literal_address:
                    continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (OSError, ValueError):
        return False


def _system_proxy_for(url: str) -> str | None:
    """Use the operating system's configured proxy for external model requests."""
    scheme = urllib.parse.urlparse(url).scheme
    proxies = urllib.request.getproxies()
    proxy = proxies.get(scheme) or proxies.get("all")
    host = urllib.parse.urlparse(url).hostname or ""
    if proxy and urllib.request.proxy_bypass(host):
        # Some desktop VPN/proxy clients resolve tunneled external domains to
        # RFC 2544 fake-IP space and also add the domain to macOS bypass rules.
        # Directing such a request to that synthetic address fails before the
        # configured provider can be reached. Keep ordinary bypass behavior,
        # but route these fake-IP destinations through the configured proxy.
        try:
            addresses = {ipaddress.ip_address(info[4][0])
                         for info in socket.getaddrinfo(host, None)}
            if not any(address in _VPN_FAKE_IP_NETWORK for address in addresses):
                return None
        except (OSError, ValueError):
            return None
    return proxy


def _strip_provider_prefix(model: str, provider: str) -> str:
    prefix = provider + "/"
    return model[len(prefix):] if model.startswith(prefix) else model


class ConfiguredAIService:
    """Resolve configured Easel providers centrally, then use the local gateway."""

    def __init__(self, *, env: dict[str, str] | None = None, timeout_seconds: float = 120):
        self.env = _read_env() if env is None else dict(env)
        self.timeout_seconds = timeout_seconds
        self.providers = self._providers()

    def _providers(self) -> list[_Provider]:
        env = self.env
        configured: dict[str, _Provider] = {}
        easel_key = env.get("EASEL_AI_API_KEY", "").strip()
        easel_base = env.get("EASEL_AI_BASE_URL", "").strip().rstrip("/")
        easel_model = env.get("EASEL_AI_MODEL", "").strip()
        easel_name = env.get("EASEL_AI_PROVIDER_NAME", "").strip()
        if _configured(easel_key) and easel_base and easel_model and easel_name.lower() != "disabled":
            configured["easel_custom"] = _Provider(
                "openai", easel_name or "当前模型", easel_base, easel_key, easel_model, {},
            )

        openai_key = env.get("OPENAI_API_KEY", "").strip()
        openai_base = env.get("OPENAI_BASE_URL", "").strip().rstrip("/")
        if _configured(openai_key) and openai_base:
            configured["openai"] = _Provider(
                "openai", "当前模型", openai_base, openai_key,
                env.get("OPENAI_MODEL", "").strip() or "deepseek-chat", {},
            )

        relay_key = env.get("EASEL_LLM_API_KEY", "").strip()
        relay_base = env.get("EASEL_LLM_BASE_URL", "").strip().rstrip("/")
        if _configured(relay_key) and relay_base:
            extra = {}
            key_header = env.get("EASEL_LLM_API_KEY_HEADER", "").strip()
            if key_header and key_header.lower() != "authorization":
                extra[key_header] = relay_key
            if env.get("EASEL_LLM_ANTHROPIC_VERSION"):
                extra["anthropic-version"] = env["EASEL_LLM_ANTHROPIC_VERSION"]
            configured["relay"] = _Provider(
                "anthropic", "当前模型", relay_base, relay_key,
                _strip_provider_prefix(env.get("CLAUDE_MODEL", "deepseek-chat").strip(), "relay"), extra,
            )

        anthropic_key = env.get("ANTHROPIC_API_KEY", "").strip()
        anthropic_base = env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").strip().rstrip("/")
        if _configured(anthropic_key):
            configured["anthropic"] = _Provider(
                "anthropic", "当前模型", anthropic_base, anthropic_key,
                _strip_provider_prefix(env.get("CLAUDE_MODEL", "claude-sonnet-4-6").strip(), "anthropic"),
                {"anthropic-version": "2023-06-01"},
            )

        # Keep the provider selected in the existing settings panel at the front.
        primary = ""
        try:
            from easel.openclaw_workspace import state_dir
            profile_path = state_dir() / "openclaw.json"
            config = json.loads(profile_path.read_text(encoding="utf-8"))
            primary = str(config.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", ""))
        except (OSError, ValueError, AttributeError):
            pass
        preferred = primary.partition("/")[0]
        if preferred not in configured and preferred == "openai":
            preferred = "openai"
        if "easel_custom" in configured:
            preferred = "easel_custom"
        order = ([preferred] if preferred in configured else []) + [key for key in ("easel_custom", "openai", "relay", "anthropic")
                                                                  if key in configured and key != preferred]
        return [configured[key] for key in order]

    def _gateway_configured(self) -> bool:
        try:
            from easel.openclaw_workspace import state_dir
            profile_path = state_dir() / "openclaw.json"
            config = json.loads(profile_path.read_text(encoding="utf-8"))
            model = config.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
            if not model:
                return False
            provider_name = str(model).partition("/")[0]
            provider = config.get("models", {}).get("providers", {}).get(provider_name, {})
            return bool(provider.get("apiKey") or provider.get("baseUrl"))
        except (OSError, ValueError, AttributeError):
            return False

    def _gateway_probe(self) -> bool:
        try:
            from easel.gateway_endpoint import healthz_url
            response = httpx.get(healthz_url(), timeout=httpx.Timeout(2, connect=1), follow_redirects=False)
            return response.status_code < 400
        except Exception:  # noqa: BLE001
            return False

    def runtime_status(self) -> AIRuntimeStatus:
        configured = bool(self.providers) or self._gateway_configured()
        had_provider_error = False
        for provider in self.providers:
            if not _safe_public_url(provider.base_url):
                had_provider_error = True
                continue
            try:
                headers = self._headers(provider)
                response = httpx.get(provider.probe_url, headers=headers,
                                     timeout=httpx.Timeout(5, connect=2), follow_redirects=False,
                                     proxy=_system_proxy_for(provider.probe_url))
                if response.status_code < 400:
                    return AIRuntimeStatus(AIRuntimeState.AVAILABLE, provider.label)
                if response.status_code in (401, 403, 404, 405):
                    # Some compatible endpoints do not expose /models; credential rejection is decisive.
                    if response.status_code in (401, 403):
                        had_provider_error = True
                    continue
                had_provider_error = True
            except (httpx.TimeoutException, httpx.NetworkError):
                continue
            except Exception:  # noqa: BLE001
                had_provider_error = True
        if self._gateway_configured() and self._gateway_probe():
            return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "当前模型")
        if not configured:
            return AIRuntimeStatus(AIRuntimeState.NOT_CONFIGURED)
        if had_provider_error:
            return AIRuntimeStatus(AIRuntimeState.ERROR)
        return AIRuntimeStatus(AIRuntimeState.UNAVAILABLE)

    @staticmethod
    def _headers(provider: _Provider) -> dict[str, str]:
        headers = {"content-type": "application/json", **provider.headers}
        if provider.kind == "anthropic":
            headers.setdefault("x-api-key", provider.api_key)
            headers.setdefault("anthropic-version", "2023-06-01")
        else:
            headers["authorization"] = f"Bearer {provider.api_key}"
        return headers

    @staticmethod
    def _response_text(provider: _Provider, payload: dict) -> str:
        if provider.kind == "anthropic":
            content = payload.get("content") or []
            return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict)).strip()
        choices = payload.get("choices") or []
        message = (choices[0] if choices else {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content or "").strip()

    def _complete_provider(self, provider: _Provider, system_prompt: str, user_prompt: str) -> str:
        if not _safe_public_url(provider.base_url):
            raise AIServiceError(AIRuntimeState.ERROR, "模型地址不安全或不可访问")
        if provider.kind == "anthropic":
            body = {"model": provider.model, "max_tokens": 7000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}]}
        else:
            body = {"model": provider.model, "temperature": 0, "max_tokens": 7000,
                    "messages": [{"role": "system", "content": system_prompt},
                                 {"role": "user", "content": user_prompt}]}
        response = httpx.post(provider.completion_url, headers=self._headers(provider), json=body,
                              timeout=httpx.Timeout(self.timeout_seconds, connect=5), follow_redirects=False,
                              proxy=_system_proxy_for(provider.completion_url))
        if response.status_code >= 400:
            state = AIRuntimeState.ERROR if response.status_code in (401, 403, 400) else AIRuntimeState.UNAVAILABLE
            raise AIServiceError(state, f"模型服务返回 HTTP {response.status_code}")
        text = self._response_text(provider, response.json())
        if not text:
            raise AIServiceError(AIRuntimeState.ERROR, "模型没有返回文本")
        return text

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        errors: list[AIServiceError] = []
        for provider in self.providers:
            try:
                return self._complete_provider(provider, system_prompt, user_prompt)
            except AIServiceError as exc:
                errors.append(exc)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                errors.append(AIServiceError(AIRuntimeState.UNAVAILABLE, type(exc).__name__))
            except Exception as exc:  # noqa: BLE001
                errors.append(AIServiceError(AIRuntimeState.ERROR, type(exc).__name__))
        try:
            from easel.gateway_endpoint import chat_completions_url
            if self._gateway_configured() and self._gateway_probe():
                response = httpx.post(
                    chat_completions_url(),
                    headers={"x-openclaw-session-key": f"agent:main:historical-classification:{uuid4().hex}"},
                    json={"model": "openclaw/default", "stream": False, "temperature": 0,
                          "max_tokens": 7000,
                          "messages": [{"role": "system", "content": system_prompt},
                                       {"role": "user", "content": user_prompt}]},
                    timeout=httpx.Timeout(self.timeout_seconds, connect=2), follow_redirects=False,
                )
                response.raise_for_status()
                text = self._response_text(_Provider("openai", "当前模型", "", "", "", {}), response.json())
                if text:
                    return text
                raise AIServiceError(AIRuntimeState.ERROR, "模型没有返回文本")
        except AIServiceError as exc:
            errors.append(exc)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            errors.append(AIServiceError(AIRuntimeState.UNAVAILABLE, type(exc).__name__))
        except Exception as exc:  # noqa: BLE001
            errors.append(AIServiceError(AIRuntimeState.ERROR, type(exc).__name__))
        if errors:
            raise errors[-1]
        raise AIServiceError(AIRuntimeState.NOT_CONFIGURED, "尚未配置 AI 模型")
