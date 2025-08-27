from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Candidate, OpportunityDiscussed
from app.services.opportunity_service import OpportunityDiscussedService
from app.services.agent_service import OpenAIAgentService
from app.deps import get_opportunity_service, get_agent_service


class _FakeOppService(OpportunityDiscussedService):
    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        pass

    def get_by_id(self, record_id: str) -> OpportunityDiscussed | None:  # type: ignore[override]
        if record_id == "a0N000000000000000":
            return None
        return OpportunityDiscussed(
            id=record_id,
            name="Test",
            candidate=Candidate(name="Jane", email="jane@example.com"),
            sum_scorecard_evaluation=10.5,
            interview_candidate_score=8.2,
        )


class _FakeAgent(OpenAIAgentService):
    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        pass

    async def analyze_opportunity(self, record: OpportunityDiscussed) -> str:  # type: ignore[override]
        return f"Analysis for {record.id}: looks strong."


def test_analysis_found() -> None:
    app.dependency_overrides[get_opportunity_service] = lambda: _FakeOppService()
    app.dependency_overrides[get_agent_service] = lambda: _FakeAgent()

    client = TestClient(app)
    resp = client.get("/api/v1/opportunity-discussed/a0N123456789012/analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "a0N123456789012"
    assert "looks strong" in body["analysis"]


def test_analysis_not_found() -> None:
    app.dependency_overrides[get_opportunity_service] = lambda: _FakeOppService()
    app.dependency_overrides[get_agent_service] = lambda: _FakeAgent()

    client = TestClient(app)
    resp = client.get("/api/v1/opportunity-discussed/a0N000000000000000/analysis")
    assert resp.status_code == 404
