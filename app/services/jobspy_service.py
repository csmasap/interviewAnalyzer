from __future__ import annotations

import csv
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from jobspy import scrape_jobs  # type: ignore

from app.core.config import Settings, get_settings
from app.models.schemas import OpportunityDiscussed

logger = logging.getLogger(__name__)


class JobSpyService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    @staticmethod
    def _collect_text_fields(record: OpportunityDiscussed) -> str:
        parts: List[str] = []
        parts.append(record.name or "")
        parts.append(record.candidate_interviews_summary or "")
        parts.append(record.ai_interview_summary or "")
        parts.append(record.scorecard_full_candidate_report or "")
        parts.append(record.interview_candidate_feedback or "")
        parts.append(record.reason_capable_of or "")
        # Prefer candidate resume for inference if available
        if record.candidate and record.candidate.resume_text:
            parts.append(record.candidate.resume_text)
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _infer_title(record: OpportunityDiscussed) -> str:
        text = JobSpyService._collect_text_fields(record).lower()

        seniority_map: List[Tuple[str, str]] = [
            (r"\bprincipal\b", "Principal"),
            (r"\bstaff\b", "Staff"),
            (r"\blead\b", "Lead"),
            (r"\bsenior\b|\bsr\.?\b", "Senior"),
            (r"\bmid\b|\bmid[- ]level\b", "Mid"),
            (r"\bjunior\b|\bjr\.?\b", "Junior"),
            (r"\bintern\b|\binternship\b", "Intern"),
        ]

        role_map: List[Tuple[str, str]] = [
            (r"\bsite reliability engineer\b|\bsre\b", "Site Reliability Engineer"),
            (r"\bdevops\b", "DevOps Engineer"),
            (r"\bfull[- ]?stack\b", "Full Stack Engineer"),
            (r"\bback[- ]?end\b", "Backend Engineer"),
            (r"\bfront[- ]?end\b", "Frontend Engineer"),
            (r"\bsoftware (engineer|developer|dev)\b", "Software Engineer"),
            (r"\bdata scientist\b", "Data Scientist"),
            (r"\bdata engineer\b", "Data Engineer"),
            (r"\bml (engineer|scientist)\b|\bmachine learning (engineer|scientist)\b", "Machine Learning Engineer"),
            (r"\bai engineer\b", "AI Engineer"),
            (r"\bdata analyst\b", "Data Analyst"),
            (r"\bproduct manager\b|\bpm\b", "Product Manager"),
            (r"\bproject manager\b", "Project Manager"),
            (r"\bqa\b|\bquality assurance\b|\btest(ing)? engineer\b", "QA Engineer"),
            (r"\bsecurity engineer\b|\bapplication security\b|\bappsec\b", "Security Engineer"),
            (r"\bcloud engineer\b", "Cloud Engineer"),
            (r"\bsolutions? architect\b", "Solutions Architect"),
            (r"\bandroid (dev(eloper)?|engineer)\b", "Android Engineer"),
            (r"\bios (dev(eloper)?|engineer)\b", "iOS Engineer"),
            (r"\bmobile (dev(eloper)?|engineer)\b", "Mobile Engineer"),
        ]

        seniority: Optional[str] = None
        for pattern, label in seniority_map:
            if re.search(pattern, text):
                seniority = label
                break

        role: Optional[str] = None
        for pattern, label in role_map:
            if re.search(pattern, text):
                role = label
                break

        # Fallbacks: prefer resume-derived text; do NOT use record.name
        if not role and record.candidate and record.candidate.resume_text:
            first_200 = record.candidate.resume_text.strip().splitlines()[:5]
            for line in first_200:
                clean = line.strip()
                if 2 <= len(clean.split()) <= 8 and any(k in clean.lower() for k in ["engineer", "developer", "manager", "scientist", "analyst", "architect", "designer"]):
                    role = clean
                    break

        # Safe generic fallback to ensure a usable search term
        if not role:
            role = "Software Engineer"

        title = f"{seniority + ' ' if seniority else ''}{role}".strip()
        logger.info("Inferred job title from record '%s': %s", record.id, title)
        return title

    def _build_search(self, record: OpportunityDiscussed, override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        inferred_title = self._infer_title(record)
        location = None

        params: Dict[str, Any] = {
            "site_name": self._settings.jobspy_sites,
            "search_term": inferred_title,
            "location": location,
            "results_wanted": self._settings.jobspy_results_wanted,
            "hours_old": self._settings.jobspy_hours_old,
            "country_indeed": self._settings.jobspy_country_indeed,
        }

        if override:
            params.update({k: v for k, v in override.items() if v is not None})

        logger.info("JobSpy search params: %s", params)
        return params

    def search(self, record: OpportunityDiscussed, override: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = self._build_search(record, override)

        try:
            # Add timeout handling
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"JobSpy scraping timed out after {self._settings.jobspy_timeout_seconds} seconds")
            
            # Set alarm for timeout (Unix-like systems)
            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self._settings.jobspy_timeout_seconds)
                jobs_df = scrape_jobs(**params)
                signal.alarm(0)  # Cancel alarm
            except AttributeError:
                # Windows doesn't support SIGALRM, fallback to basic scraping
                logger.warning("Timeout handling not available on this platform")
                jobs_df = scrape_jobs(**params)
        except TimeoutError as exc:
            logger.error("JobSpy scraping timed out: %s", exc)
            return []  # Return empty list instead of raising
        except Exception as exc:
            logger.exception("JobSpy scrape failure: %s", exc)
            return []  # Return empty list instead of raising

        if jobs_df is None:
            return []

        records: List[Dict[str, Any]] = jobs_df.to_dict(orient="records")  # type: ignore[attr-defined]
        trimmed: List[Dict[str, Any]] = []
        keep_fields = {
            "site",
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "job_type",
            "interval",
            "min_amount",
            "max_amount",
            "currency",
            "is_remote",
            "job_level",
            "job_function",
            "description"
        }
        for row in records:
            trimmed.append({k: row.get(k) for k in keep_fields})
        return trimmed
