from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from simple_salesforce import Salesforce

from .config import Settings

logger = logging.getLogger(__name__)

_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")


def _sanitize_salesforce_id(record_id: str) -> str:
    if not _VALID_ID_RE.match(record_id):
        raise ValueError("Invalid Salesforce Id format. Must be 15–18 alphanumeric characters.")
    return record_id


class SalesforceClient:
    """Simplified Salesforce client for skill interview app."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sf: Optional[Salesforce] = None

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
            self._sf = self._connect()
        return self._sf

    def query_contact_by_id(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Returns the raw Salesforce Contact record or None if not found."""
        contact_id = _sanitize_salesforce_id(contact_id)
        soql = (
            "SELECT Id, Name, Email, Candidate_s_Resume_TXT__c "
            "FROM Contact WHERE Id = '{}'".format(contact_id)
        )
        logger.info("SOQL query for Contact: %s", soql)
        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)
        logger.info("Contact query returned %d records for ID %s", total_size, contact_id)
        if total_size == 0:
            return None
        records = result.get("records", [])
        if not records:
            return None
        # simple-salesforce adds 'attributes' metadata; drop it for cleanliness
        record = {k: v for k, v in records[0].items() if k != "attributes"}
        return record