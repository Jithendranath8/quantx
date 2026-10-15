"""
QuantX — Internal cron endpoint tests.

The scheduled-jobs endpoint stands in for an always-on worker on free
deployments. It must be disabled without a secret, reject a wrong secret, 404 an
unknown job, and run a known job when the secret matches.
"""

import pytest
from httpx import AsyncClient

import app.api.v1.endpoints.internal as internal
from app.core.config import get_settings


async def test_disabled_without_secret(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", "")
    resp = await client.post("/api/v1/internal/jobs/health")
    assert resp.status_code == 503


async def test_rejects_wrong_secret(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", "right-secret")
    resp = await client.post(
        "/api/v1/internal/jobs/health", headers={"X-Cron-Secret": "wrong-secret"}
    )
    assert resp.status_code == 401


async def test_unknown_job_is_404(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    resp = await client.post(
        "/api/v1/internal/jobs/does_not_exist", headers={"X-Cron-Secret": "s3cret"}
    )
    assert resp.status_code == 404


async def test_runs_known_job_with_valid_secret(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")

    # Swap in a safe job so the dispatch path is tested without DB/network.
    async def _fake_job() -> dict[str, bool]:
        return {"ran": True}

    monkeypatch.setitem(internal._JOBS, "health", _fake_job)
    resp = await client.post(
        "/api/v1/internal/jobs/health", headers={"X-Cron-Secret": "s3cret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"] == "health"
    assert body["result"] == {"ran": True}
