"""Meta Model API client wrapper (https://api.meta.ai/v1/).

Offline-testable: all HTTP goes through an injectable transport callable
defaulting to urllib. Reads MODEL_API_KEY for auth; META_API_BASE_URL
overrides the base URL (tests pin it to a closed port to prove zero network).

Fixture shapes mirror the operator's 2026-10-26 live probes (H2_LIVE_PROBE_RECEIPT):
muse-spark-1.3 emits reasoning tokens under usage.completion_tokens_details —
budget max_tokens generously.
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.meta.ai/v1/"
KEY_ENV = "MODEL_API_KEY"
BASE_URL_ENV = "META_API_BASE_URL"


class MetaAPIError(RuntimeError):
    """Non-2xx from the API other than the specifically-handled codes."""


class MissingAPIKeyError(MetaAPIError):
    """MODEL_API_KEY is not set in the environment."""


class BillingNotConfiguredError(MetaAPIError):
    """HTTP 402 billing_not_configured — credits/card not active on the team."""


def _urllib_transport(request):
    """Default transport: returns (status, body_bytes). Never returns a socket."""
    try:
        with urllib.request.urlopen(request) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class MetaClient:
    def __init__(self, base_url=None, api_key=None, transport=None):
        self.base_url = base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        self.api_key = api_key if api_key is not None else os.environ.get(KEY_ENV)
        if not self.api_key:
            raise MissingAPIKeyError(
                f"{KEY_ENV} is not set — export it (e.g. from "
                f"~/.config/llm_api/keys.env) or pass api_key explicitly"
            )
        self._transport = transport or _urllib_transport

    def _request(self, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST" if body is not None else "GET",
        )
        status, raw = self._transport(req)
        try:
            parsed = json.loads(raw.decode())
        except (ValueError, UnicodeDecodeError):
            parsed = {"raw": raw.decode(errors="replace")}
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if status == 402 and isinstance(error, dict) and error.get("code") == "billing_not_configured":
            raise BillingNotConfiguredError(
                "402 billing_not_configured: credits/payment method not active "
                "for this team — see billing page; usage draws credits before card"
            )
        if status >= 400:
            raise MetaAPIError(f"{req.method} {path} -> HTTP {status}: {parsed}")
        return parsed

    def list_models(self):
        """GET /models -> parsed JSON with data[].id roster."""
        return self._request("models")

    def chat(self, model, messages, max_tokens=512, **extra):
        """POST /chat/completions -> parsed JSON response.

        max_tokens defaults generously (512) because muse-spark models spend
        the budget on reasoning tokens before any visible content.
        """
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
        payload.update(extra)
        return self._request("chat/completions", payload=payload)

    @staticmethod
    def usage_summary(response):
        """Flatten a chat response's usage, surfacing reasoning-token detail."""
        usage = dict(response.get("usage", {}))
        details = usage.pop("completion_tokens_details", {}) or {}
        summary = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "reasoning_tokens": details.get("reasoning_tokens", 0),
        }
        return summary
