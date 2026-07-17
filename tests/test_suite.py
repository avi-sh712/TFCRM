from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from talentforge import auth, email_service, graph_engine, ingestion


JWT_SECRET = "t" * 48
WEBHOOK_SECRET = "w" * 48


def _jwt_token(*, expires_at: datetime, role: str = "csm") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "role": role,
            "scope": f"role:{role}",
            "type": "access",
            "iss": "talentforge-api",
            "aud": "talentforge-api",
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "jti": str(uuid4()),
        },
        JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )


def test_auth_decodes_valid_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(auth.JWT_SECRET_KEY_ENV, JWT_SECRET)
    token = _jwt_token(expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))

    claims = auth._decode_access_token(token)

    assert claims.role.value == "csm"


def test_auth_rejects_expired_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(auth.JWT_SECRET_KEY_ENV, JWT_SECRET)
    token = _jwt_token(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))

    with pytest.raises(HTTPException) as raised:
        auth._decode_access_token(token)

    assert raised.value.status_code == 401


def test_webhook_hmac_sha256_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ingestion.WEBHOOK_SECRET_ENV, WEBHOOK_SECRET)
    body = b'{"event_type":"error","customer_id":"00000000-0000-0000-0000-000000000001"}'
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    ingestion._verify_webhook_signature(body, f"sha256={signature}")

    with pytest.raises(HTTPException) as raised:
        ingestion._verify_webhook_signature(body, "0" * 64)
    assert raised.value.status_code == 401


def test_duplicate_idempotency_key_is_blocked_within_hour() -> None:
    customer_id = uuid4()
    hour = datetime(2026, 7, 14, 10, tzinfo=timezone.utc)

    first_key = ingestion.build_idempotency_key(customer_id, "timeout", hour)
    duplicate_key = ingestion.build_idempotency_key(customer_id, "timeout", hour)
    next_hour_key = ingestion.build_idempotency_key(
        customer_id,
        "timeout",
        hour + timedelta(hours=1),
    )

    assert first_key == duplicate_key
    assert first_key != next_hour_key


def test_graph_escalates_at_retry_ceiling_without_another_retry() -> None:
    state = graph_engine.make_initial_state("customer-1", {}, max_retries=3)
    state["retry_count"] = 3
    state["tool_errors"] = ["Read-only customer history retrieval failed or timed out."]

    route = graph_engine.TalentForgeGraphEngine._route_after_tool_call(state)

    assert route == "escalate"
    assert route != "retry"


@pytest.mark.asyncio
async def test_company_agent_graph_awaits_async_node_factory() -> None:
    async def node(state: graph_engine.CompanyAgentState) -> dict[str, object]:
        return {"output": {"company_id": state["company_id"]}}

    graph = graph_engine._compile_company_agent_graph(lambda state: node(state))
    result = await graph.ainvoke(
        {"company_id": "customer-1", "config": {}, "output": {}},
    )

    assert result["output"] == {"company_id": "customer-1"}


@pytest.mark.asyncio
async def test_resend_adapter_uses_expected_request_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"id": "email_123"}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 15.0

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            requests.append({"url": url, **kwargs})
            return FakeResponse()

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "TalentForge <onboarding@resend.dev>")
    monkeypatch.setattr(email_service.httpx, "AsyncClient", FakeClient)

    message_id = await email_service.send_outreach_email(
        "owner@example.com", "A quick check-in", "<p>Hello</p>"
    )

    assert message_id == "email_123"
    assert requests == [{
        "url": email_service.RESEND_EMAILS_URL,
        "headers": {"Authorization": "Bearer re_test_key"},
        "json": {
            "from": "TalentForge <onboarding@resend.dev>",
            "to": ["owner@example.com"],
            "subject": "A quick check-in",
            "html": "<p>Hello</p>",
        },
    }]
