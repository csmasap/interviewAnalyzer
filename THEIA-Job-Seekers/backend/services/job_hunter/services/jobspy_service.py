from __future__ import annotations

import csv
import logging
from typing import Any, Dict, List, Optional

from jobspy import scrape_jobs  # type: ignore

from services.job_hunter.core.config import Settings, get_settings
from services.job_hunter.models.schemas import OpportunityDiscussed

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
    def _infer_title(record: OpportunityDiscussed) -> Optional[str]:
        # Regex-based inference removed to avoid inaccurate defaults
        logger.info("Title inference disabled for record '%s' (no regex)", record.id)
        return None

    def _build_params(self, record: OpportunityDiscussed, override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

        if not params.get("search_term"):
            raise ValueError("No search query available. Provide search_term or set use_ai_query=true.")

        safe_params = dict(params)
        if isinstance(safe_params.get("search_term"), str):
            safe_params["search_term"] = f"len={len(safe_params['search_term'])}"
        logger.info(
            "Stage 3: JobSpy params (sites=%s, query=%s, location=%s, results=%s, hours_old=%s, country=%s)",
            safe_params.get("site_name"),
            safe_params.get("search_term"),
            safe_params.get("location"),
            safe_params.get("results_wanted"),
            safe_params.get("hours_old"),
            safe_params.get("country_indeed"),
        )
        return params

    def search(self, record: OpportunityDiscussed, override: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = self._build_params(record, override)

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
        logger.info("Stage 4: Scrape returned %d records", len(records))
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
