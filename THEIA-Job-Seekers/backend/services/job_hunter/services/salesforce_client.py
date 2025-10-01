from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, Optional

from simple_salesforce import Salesforce  # type: ignore

from services.job_hunter.core.config import Settings

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
        logger.info("SOQL query by ID: %s", soql)
        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)
        logger.info("Direct query returned %d records for ID %s", total_size, record_id)
        if total_size == 0:
            return None
        records = result.get("records", [])
        if not records:
            return None
        # simple-salesforce adds 'attributes' metadata; drop it for cleanliness
        record = {k: v for k, v in records[0].items() if k != "attributes"}
        return record

    def query_opportunity_discussed_by_candidate(self, candidate_id: str, limit: int = 6) -> list[Dict[str, Any]]:
        """Returns the latest Salesforce records for TR1__Opportunity_Discussed__c by candidate ID."""
        candidate_id = _sanitize_salesforce_id(candidate_id)
        soql = (
            "SELECT Id, Name, CreatedDate, "
            "TR1__Candidate__r.Name, TR1__Candidate__r.Email, TR1__Candidate__r.Candidate_s_Resume_TXT__c, "
            "Sum_ScoreCard_Evaulation__c, Reason_Capable_of__c, Candidate_Interviews_Summary__c, "
            "Salary_Expectations__c, Scorecard_Full_Candidate_Report__c, AI_Interview_Summary__c, "
            "Interview_Candidate_Score__c, Interview_Candidate_Feedback__c "
            "FROM TR1__Opportunity_Discussed__c "
            "WHERE TR1__Candidate__c = '{}' "
            "ORDER BY CreatedDate DESC "
            "LIMIT {}".format(candidate_id, limit)
        )
        logger.info("SOQL query by candidate: %s", soql)
        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)
        logger.info("Query returned %d records for candidate %s", total_size, candidate_id)
        if total_size == 0:
            return []
        records = result.get("records", [])
        # simple-salesforce adds 'attributes' metadata; drop it for cleanliness
        cleaned_records = []
        for record in records:
            cleaned_record = {k: v for k, v in record.items() if k != "attributes"}
            cleaned_records.append(cleaned_record)
        return cleaned_records

    def query_contact_by_id(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Returns the raw Salesforce Contact record or None if not found."""
        contact_id = _sanitize_salesforce_id(contact_id)
        soql = (
            "SELECT Id, Name, Email, Candidate_s_Resume_TXT__c, (SELECT AI_Interview_Summary__c, Screening_Transcript__c FROM TR1__Opportunities_Discussed__r WHERE TR1__Job__r.Id = 'a0WPM0000045Kjl2AE')"
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

    def create_ai_interview_record(self, candidate_id: str, candidate_analysis: str, career_goal: str, career_guidance: str) -> str:
        """Create a new AI_Interview__c record in Salesforce."""
        candidate_id = _sanitize_salesforce_id(candidate_id)

        # Prepare the record data
        record_data = {
            'Candidate__c': candidate_id,
            'Candidate_OD_Analisys__c': candidate_analysis[:32768] if candidate_analysis else '',  # Truncate if too long
            'Career_Goal__c': career_goal[:255] if career_goal else '',  # Truncate if too long
            'Career_Guidance__c': career_guidance[:32768] if career_guidance else ''  # Truncate if too long
        }

        logger.debug("Creating AI_Interview__c record: %s", record_data)

        sf = self.get_client()
        result = sf.AI_Interview__c.create(record_data)

        if result.get('success'):
            record_id = result.get('id')
            logger.info("Successfully created AI_Interview__c record: %s", record_id)
            return record_id
        else:
            errors = result.get('errors', [])
            error_msg = f"Failed to create AI_Interview__c record: {errors}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def query_application_record_by_id(self, application_id: str) -> Optional[Dict[str, Any]]:
        """Query TR1__Application__c record by ID to get ISA_Link__c field."""
        application_id = _sanitize_salesforce_id(application_id)

        soql = (
            "SELECT Id, ISA_Link__c FROM TR1__Application__c "
            "WHERE Id = '{}' "
            "LIMIT 1".format(application_id)
        )

        logger.debug("Querying TR1__Application__c record: %s", soql)

        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)

        if total_size > 0:
            records = result.get("records", [])
            if records:
                record = records[0]
                return {k: v for k, v in record.items() if k != "attributes"}

        logger.debug("TR1__Application__c record not found")
        return None

    def create_opportunity_discussed_record(self, candidate_id: str, application_id: Optional[str] = None,
                                           screening_transcript: Optional[str] = None, ai_interview_summary: Optional[str] = None,
                                           job_id: str = 'a0WPM0000045Kjl2AE',
                                           record_type_id: str = '012PM000000pSYYYA2') -> str:
        """Create a new TR1__Opportunity_Discussed__c record for interview results."""
        candidate_id = _sanitize_salesforce_id(candidate_id)
        if application_id:
            application_id = _sanitize_salesforce_id(application_id)
        job_id = _sanitize_salesforce_id(job_id)

        # Prepare the record data
        record_data = {
            'TR1__Candidate__c': candidate_id,
            'TR1__Job__c': job_id,
            'RecordTypeId': record_type_id
        }

        if screening_transcript:
            record_data['Screening_Transcript__c'] = screening_transcript
        if ai_interview_summary:
            record_data['AI_Interview_Summary__c'] = ai_interview_summary
        if application_id:
            record_data['Application_online__c'] = application_id

        logger.debug("Creating TR1__Opportunity_Discussed__c record: %s", record_data)

        sf = self.get_client()
        result = sf.TR1__Opportunity_Discussed__c.create(record_data)

        if result.get('success'):
            record_id = result.get('id')
            logger.info("Successfully created TR1__Opportunity_Discussed__c record: %s", record_id)
            return record_id
        else:
            errors = result.get('errors', [])
            error_msg = f"Failed to create TR1__Opportunity_Discussed__c record: {errors}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def query_application_record_exists(self, applicant_id: str, job_id: str = 'a0WPM0000045Kjl2AE') -> Optional[str]:
        """Check if TR1__Application__c record already exists for the given applicant and job."""
        applicant_id = _sanitize_salesforce_id(applicant_id)
        job_id = _sanitize_salesforce_id(job_id)

        soql = (
            "SELECT Id FROM TR1__Application__c "
            "WHERE TR1__Applicant__c = '{}' AND TR1__Job__c = '{}' "
            "LIMIT 1".format(applicant_id, job_id)
        )

        logger.debug("Checking for existing TR1__Application__c record: %s", soql)

        sf = self.get_client()
        result = sf.query(soql)
        total_size = result.get("totalSize", 0)

        if total_size > 0:
            records = result.get("records", [])
            if records:
                existing_record_id = records[0].get("Id")
                logger.info("Found existing TR1__Application__c record: %s", existing_record_id)
                return existing_record_id

        logger.debug("No existing TR1__Application__c record found")
        return None

    def create_application_record(self, applicant_id: str, job_id: str = 'a0WPM0000045Kjl2AE', source: str = 'ASAP Website') -> str:
        """Create a new TR1__Application__c record in Salesforce, checking for duplicates first."""
        applicant_id = _sanitize_salesforce_id(applicant_id)
        job_id = _sanitize_salesforce_id(job_id)

        # Check if record already exists
        existing_record_id = self.query_application_record_exists(applicant_id, job_id)
        if existing_record_id:
            logger.info("TR1__Application__c record already exists: %s", existing_record_id)
            return existing_record_id

        # Prepare the record data
        record_data = {
            'TR1__Applicant__c': applicant_id,
            'TR1__Source__c': source,
            'TR1__Job__c': job_id
        }

        logger.debug("Creating TR1__Application__c record: %s", record_data)

        sf = self.get_client()
        result = sf.TR1__Application__c.create(record_data)

        if result.get('success'):
            record_id = result.get('id')
            logger.info("Successfully created TR1__Application__c record: %s", record_id)
            return record_id
        else:
            errors = result.get('errors', [])
            error_msg = f"Failed to create TR1__Application__c record: {errors}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
