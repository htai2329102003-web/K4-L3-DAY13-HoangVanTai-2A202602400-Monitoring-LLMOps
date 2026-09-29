from __future__ import annotations

import json
import asyncio
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_chat_correlates_requests_enriches_logs_and_scrubs_pii(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_requests() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            first = await client.post(
                "/chat",
                headers={"x-request-id": "external-demo-01"},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": (
                        "4111111111111111 demo@example.com 0901234567 012345678901"
                    ),
                },
            )
            second = await client.post(
                "/chat",
                json={
                    "user_id": "student-02",
                    "session_id": "session-02",
                    "feature": "summary",
                    "message": "Summarize observability",
                },
            )
            return [first, second]

    responses = asyncio.run(send_requests())
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].headers["x-request-id"] == "external-demo-01"
    generated_id = responses[1].headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", generated_id)
    assert float(responses[0].headers["x-response-time-ms"]) >= 0

    raw_logs = log_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_logs.splitlines()]
    api_events = [event for event in events if event.get("service") == "api"]
    assert {event["correlation_id"] for event in api_events} == {
        "external-demo-01",
        generated_id,
    }
    expected_context = {
        "external-demo-01": ("session-01", "qa"),
        generated_id: ("session-02", "summary"),
    }
    for event in api_events:
        assert event["user_id_hash"]
        assert (event["session_id"], event["feature"]) == expected_context[
            event["correlation_id"]
        ]
        assert event["model"]
        assert event["env"]

    for raw_pii in (
        "demo@example.com",
        "0901234567",
        "012345678901",
        "4111111111111111",
    ):
        assert raw_pii not in raw_logs
    assert "REDACTED_EMAIL" in raw_logs
    assert "REDACTED_PHONE_VN" in raw_logs
    assert "REDACTED_CCCD" in raw_logs
    assert "REDACTED_CREDIT_CARD" in raw_logs
