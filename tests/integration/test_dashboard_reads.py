from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from shrike.adapters.persistence.dashboard import SqlDashboardReader
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import DEMO_TIME, demo_id
from shrike.adapters.persistence.models import ReviewJob
from shrike.domain.access import ReadScope, RepositoryGrant

pytestmark = pytest.mark.integration
SCOPE = ReadScope((RepositoryGrant(710001, 810001),))


def test_scoped_metrics_denominators_window_and_no_terminal_data(seeded_database: Database) -> None:
    with seeded_database.session() as session:
        reader = SqlDashboardReader(session)
        metrics = reader.metrics(SCOPE, 30, now=DEMO_TIME + timedelta(days=1))
        assert metrics.repositories == 1 and metrics.reviews == 4 and metrics.findings == 3
        assert metrics.completed == 1 and metrics.failed == 1
        assert metrics.success_rate == 50 and metrics.failure_rate == 50
        assert metrics.average_processing_seconds == 10
        assert metrics.severity_counts["high"] == 1
        empty = reader.metrics(ReadScope(()), 30)
        assert empty.reviews == 0 and empty.findings == 0 and empty.repositories == 0
        assert empty.success_rate is None and empty.average_processing_seconds is None
        assert reader.metrics(SCOPE, 1, now=DEMO_TIME + timedelta(days=3)).reviews == 0


def test_dashboard_filters_pagination_detail_evidence_and_publication(
    client: TestClient, seeded_database: Database
) -> None:
    response = client.get("/v1/dashboard/reviews", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1 and response.json()["next_cursor"]
    assert response.json()["items"][0]["repository_name"] == "payments-api"
    next_page = client.get(
        "/v1/dashboard/reviews", params={"limit": 1, "cursor": response.json()["next_cursor"]}
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["id"] != response.json()["items"][0]["id"]
    assert (
        client.get("/v1/dashboard/reviews", params={"state": "failed"}).json()["items"][0]["state"]
        == "failed"
    )
    assert (
        client.get("/v1/dashboard/repositories", params={"search": "missing"}).json()["items"] == []
    )
    job_id = demo_id("completed")
    detail = client.get(f"/v1/dashboard/reviews/{job_id}").json()
    assert detail["publication"]["state"] == "not_requested"
    assert len(detail["findings"]["items"]) == 3 and detail["coverage"] is None
    assert all(f["snippet"] is None for f in detail["findings"]["items"])
    with seeded_database.session() as session, session.begin():
        job = session.get(ReviewJob, job_id)
        assert job
        job.result = {
            "status": "partial",
            "coverage": {"selected_files": 1, "changed_lines": 8, "skipped": {"unsupported": 1}},
            "findings": [
                {
                    "path": "src/storage.py",
                    "line": 18,
                    "rule": "demo.parameterized-query",
                    "evidence": "synthetic evidence only",
                }
            ],
        }
    detail = client.get(f"/v1/dashboard/reviews/{job_id}", params={"severity": "high"}).json()
    assert len(detail["findings"]["items"]) == 1
    assert detail["findings"]["items"][0]["snippet"] == "synthetic evidence only"
    assert detail["findings"]["items"][0]["github_url"].startswith(
        "https://github.com/shrike-demo/payments-api/blob/"
    )
    assert detail["coverage"]["skipped_files"] == 1 and detail["analysis_status"] == "partial"
    assert client.get(f"/v1/dashboard/reviews/{demo_id('other-job')}").status_code == 404


def test_scoped_operations_and_fixed_settings_do_not_claim_heartbeat(client: TestClient) -> None:
    data = client.get("/v1/dashboard/operations").json()
    assert data["pending"] == 1 and data["running"] == 1
    assert data["active_leases"] == 0 and data["expired_leases"] == 1
    assert (
        data["worker_heartbeat"] == "unavailable" and data["broker_reachability"] == "unavailable"
    )
    assert client.get("/v1/dashboard/settings").json()["publishing"] == "report_only"
    assert client.post("/v1/dashboard/settings", json={"ai_provider": "openai"}).status_code == 405


@pytest.mark.parametrize("path", ["repositories", "reviews", "metrics", "operations", "settings"])
def test_dashboard_denies_unauthenticated_requests(client: TestClient, path: str) -> None:
    client.headers.pop("Authorization")
    assert client.get(f"/v1/dashboard/{path}").status_code == 401
