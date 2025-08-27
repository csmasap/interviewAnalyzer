from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional

from app.models.schemas import Candidate, OpportunityDiscussed
from app.services.salesforce_client import SalesforceClient


def _normalize_string(value: Any, *, max_length: int | None = None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, bool)):
        text = str(value)
    elif isinstance(value, (dict, list, tuple, set)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
    elif isinstance(value, bytes):
        try:
            text = value.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = str(value)
    else:
        text = str(value).strip()

    text = "".join(ch for ch in text if ch.isprintable() or ch in ("\n", "\r", "\t"))

    if max_length is not None and len(text) > max_length:
        text = text[: max_length]

    return text or None


def _normalize_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.replace(",", ""))
        except Exception:
            return None
    else:
        return None

    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _extract_candidate(raw: Dict[str, Any]) -> Optional[Candidate]:
    rel = raw.get("TR1__Candidate__r")
    if not isinstance(rel, dict):
        return None
    return Candidate(
        name=_normalize_string(rel.get("Name")),
        email=_normalize_string(rel.get("Email")),
        resume_text=_normalize_string(rel.get("Candidate_s_Resume_TXT__c"), max_length=10000),
    )


def _to_domain(raw: Dict[str, Any]) -> OpportunityDiscussed:
    return OpportunityDiscussed(
        id=_normalize_string(raw.get("Id")) or "",
        name=_normalize_string(raw.get("Name")),
        candidate=_extract_candidate(raw),
        sum_scorecard_evaluation=_normalize_float(raw.get("Sum_ScoreCard_Evaulation__c")),
        reason_capable_of=_normalize_string(raw.get("Reason_Capable_of__c")),
        candidate_interviews_summary=_normalize_string(raw.get("Candidate_Interviews_Summary__c")),
        salary_expectations=_normalize_string(raw.get("Salary_Expectations__c"), max_length=2048),
        scorecard_full_candidate_report=_normalize_string(raw.get("Scorecard_Full_Candidate_Report__c")),
        ai_interview_summary=_normalize_string(raw.get("AI_Interview_Summary__c")),
        interview_candidate_score=_normalize_float(raw.get("Interview_Candidate_Score__c")),
        interview_candidate_feedback=_normalize_string(raw.get("Interview_Candidate_Feedback__c")),
    )


class OpportunityDiscussedService:
    def __init__(self, salesforce_client: SalesforceClient) -> None:
        self._sf_client = salesforce_client

    def get_by_id(self, record_id: str) -> Optional[OpportunityDiscussed]:
        raw = self._sf_client.query_opportunity_discussed_by_id(record_id=record_id)
        if raw is None:
            return None
        return _to_domain(raw)
