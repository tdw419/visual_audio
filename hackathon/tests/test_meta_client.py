"""h2 — Meta Model API client wrapper, OFFLINE fixture tests.

Zero network: the client under test gets an injected transport; the base URL
env override points at a closed port for the whole module, so any accidental
real connection fails loudly instead of silently passing.
"""
import json
import pathlib
import urllib.error

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
# Closed port: if anything under test actually dials out, these tests error.


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeTransport:
    """Records requests; replies with (status, body_bytes) — no sockets."""

    def __init__(self, status=200, body=b""):
        self.status = status
        self.body = body
        self.requests = []

    @classmethod
    def from_fixture(cls, name, status=200):
        return cls(status=status, body=(FIXTURES / name).read_bytes())

    def __call__(self, request):
        self.requests.append(request)
        return self.status, self.body


def _client(transport):
    from hackathon.demo.meta_client import MetaClient

    return MetaClient(
        base_url="http://127.0.0.1:9/v1/",
        api_key="offline-test-dummy-key",
        transport=transport,
    )


def test_models_list_parses_roster():
    t = FakeTransport.from_fixture("models_list.json")
    client = _client(t)
    models = client.list_models()
    ids = [m["id"] for m in models["data"]]
    assert "sam-3.1" in ids and "muse-spark-1.3" in ids
    assert t.requests[0].full_url == "http://127.0.0.1:9/v1/models"
    assert t.requests[0].get_header("Authorization") == "Bearer offline-test-dummy-key"


def test_chat_parses_usage_and_reasoning_tokens():
    t = FakeTransport.from_fixture("chat_completion.json")
    client = _client(t)
    resp = client.chat(
        model="muse-spark-1.3",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=512,
    )
    assert resp["choices"][0]["finish_reason"] == "length"
    usage = client.usage_summary(resp)
    assert usage["prompt_tokens"] == 16
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 21
    assert usage["reasoning_tokens"] == 3


def test_chat_generous_budget_is_passed_through():
    t = FakeTransport.from_fixture("chat_completion.json")
    client = _client(t)
    client.chat(model="muse-spark-1.3", messages=[], max_tokens=512)
    body = json.loads(t.requests[0].data.decode())
    assert body["max_tokens"] == 512


def test_402_billing_not_configured_raises_clear_error():
    err_body = json.dumps(
        {"error": {"code": "billing_not_configured", "message": "no billing"}}
    ).encode()
    t = FakeTransport(status=402, body=err_body)
    client = _client(t)
    with pytest.raises(Exception) as exc:
        client.chat(model="muse-spark-1.3", messages=[], max_tokens=512)
    from hackathon.demo.meta_client import BillingNotConfiguredError

    assert isinstance(exc.value, BillingNotConfiguredError)
    assert "billing_not_configured" in str(exc.value)


def test_missing_model_api_key_is_a_clear_error(monkeypatch):
    from hackathon.demo.meta_client import MetaClient, MissingAPIKeyError

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError) as exc:
        MetaClient(base_url="http://127.0.0.1:9/v1/", transport=FakeTransport())
    assert "MODEL_API_KEY" in str(exc.value)


def test_base_url_env_override_is_honored(monkeypatch):
    from hackathon.demo.meta_client import MetaClient

    monkeypatch.setenv("META_API_BASE_URL", "http://127.0.0.1:9/override/")
    t = FakeTransport.from_fixture("models_list.json")
    client = MetaClient(api_key="offline-test-dummy-key", transport=t)
    client.list_models()
    assert t.requests[0].full_url == "http://127.0.0.1:9/override/models"


def test_no_key_material_in_hackathon_subtree():
    """Defensive scan: no long secret-looking literals under hackathon/."""
    import re

    pattern = re.compile(r"\b(sk|xapikey|api[_-]?key)['\"\s:=]+[A-Za-z0-9+/_-]{24,}", re.I)
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, ValueError):
            continue
        if pattern.search(text):
            offenders.append(str(p))
    assert offenders == [], f"possible key material in: {offenders}"
