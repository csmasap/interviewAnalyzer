from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, Optional

from simple_salesforce import Salesforce  # type: ignore

from app.core.config import Settings

logger = logging.getLogger(__name__)


_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")


def _sanitize_salesforce_id(record_id: str) -> str:
    if not _VALID_ID_RE.match(record_id):
        raise ValueError("Invalid Salesforce Id format. Must be 15–18 alphanumeric characters.")
    return record_id


class SalesforceClient:
    """Thread-safe lazy connector for Salesforce using simple-salesforce."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sf: Optional[Salesforce] = None
        self._lock = threading.Lock()

    def _connect(self) -> Salesforce:
        if not (self._settings.salesforce_username and self._settings.salesforce_password and self._settings.salesforce_security_token):
            raise RuntimeError(
                "Salesforce credentials are not set. Please configure SALESFORCE_USERNAME, SALESFORCE_PASSWORD, and SALESFORCE_SECURITY_TOKEN in the environment."
            )
        logger.info("Connecting to Salesforce domain=%s", self._settings.salesforce_domain)
        sf = Salesforce(
            username=self._settings.salesforce_username,
            password=self._settings.salesforce_password,
            security_token=self._settings.salesforce_security_token,
            domain=self._settings.salesforce_domain,
        )
        logger.info("Connected to Salesforce successfully")
        return sf

    def get_client(self) -> Salesforce:
        if self._sf is None:
            with self._lock:
                if self._sf is None:
                    self._sf = self._connect()
        return self._sf

    def query_opportunity_discussed_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Returns the raw Salesforce record for TR1__Opportunity_Discussed__c or None if not found."""
        record_id = _sanitize_salesforce_id(record_id)
        soql = (
            "SELECT Id, Name, "
            "TR1__Candidate__r.Name, TR1__Candidate__r.Email,TR1__Candidate__r.Candidate_s_Resume_TXT__c,"
            "Sum_ScoreCard_Evaulation__c, Reason_Capable_of__c, Candidate_Interviews_Summary__c, "
            "Salary_Expectations__c, Scorecard_Full_Candidate_Report__c, AI_Interview_Summary__c, "
            "Interview_Candidate_Score__c, Interview_Candidate_Feedback__c "
            "FROM TR1__Opportunity_Discussed__c WHERE Id = '{}'".format(record_id)
        )
        logger.debug("SOQL query: %s", soql)
        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)
        if total_size == 0:
            return None
        records = result.get("records", [])
        if not records:
            return None
        # simple-salesforce adds 'attributes' metadata; drop it for cleanliness
        record = {k: v for k, v in records[0].items() if k != "attributes"}
        return record
