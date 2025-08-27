from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Candidate, OpportunityDiscussed
from app.services.opportunity_service import OpportunityDiscussedService
from app.deps import get_opportunity_service


class _FakeService(OpportunityDiscussedService):
    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        pass

    def get_by_id(self, record_id: str) -> OpportunityDiscussed | None:  # type: ignore[override]
        if record_id == "a0N000000000000000":  # 18 chars
            return None
        return OpportunityDiscussed(
            id=record_id,
            name="Test",
            candidate=Candidate(name="Jane", email="jane@example.com"),
            sum_scorecard_evaluation=10.5,
        )


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_found() -> None:
    app.dependency_overrides[get_opportunity_service] = lambda: _FakeService()

    client = TestClient(app)
    resp = client.get("/api/v1/opportunity-discussed/a0N123456789012")  # 15 chars
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "a0N123456789012"
    assert body["candidate"]["email"] == "jane@example.com"



def test_get_not_found() -> None:
    app.dependency_overrides[get_opportunity_service] = lambda: _FakeService()

    client = TestClient(app)
    resp = client.get("/api/v1/opportunity-discussed/a0N000000000000000")  # 18 chars
    assert resp.status_code == 404
