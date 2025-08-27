from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WorkflowState:
    def __init__(self, record_id: str, job_description: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.record_id = record_id
        self.job_description = job_description
        self.created_at = datetime.utcnow()
        self.current_step = "init"
        self.data: Dict[str, Any] = {}
        self.completed = False
        self.error: Optional[str] = None

    def is_expired(self, ttl_minutes: int = 60) -> bool:
        return datetime.utcnow() > self.created_at + timedelta(minutes=ttl_minutes)

    def update_step(self, step: str, data: Dict[str, Any]) -> None:
        self.current_step = step
        self.data.update(data)
        logger.info(f"Workflow {self.id} updated to step: {step}")

    def mark_completed(self) -> None:
        self.completed = True
        self.current_step = "completed"

    def mark_error(self, error: str) -> None:
        self.error = error
        self.current_step = "error"


class WorkflowStateService:
    """In-memory state manager for multi-step workflows. In production, use Redis or DB."""
    
    def __init__(self):
        self._states: Dict[str, WorkflowState] = {}

    def create_workflow(self, record_id: str, job_description: Optional[str] = None) -> WorkflowState:
        state = WorkflowState(record_id, job_description)
        self._states[state.id] = state
        logger.info(f"Created workflow {state.id} for record {record_id}")
        return state

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        state = self._states.get(workflow_id)
        if state and state.is_expired():
            self.cleanup_workflow(workflow_id)
            return None
        return state

    def update_workflow(self, workflow_id: str, step: str, data: Dict[str, Any]) -> Optional[WorkflowState]:
        state = self.get_workflow(workflow_id)
        if state:
            state.update_step(step, data)
        return state

    def cleanup_workflow(self, workflow_id: str) -> None:
        if workflow_id in self._states:
            del self._states[workflow_id]
            logger.info(f"Cleaned up workflow {workflow_id}")

    def cleanup_expired(self, ttl_minutes: int = 60) -> int:
        """Clean up expired workflows. Returns count of cleaned workflows."""
        expired = [wf_id for wf_id, state in self._states.items() if state.is_expired(ttl_minutes)]
        for wf_id in expired:
            self.cleanup_workflow(wf_id)
        return len(expired)
