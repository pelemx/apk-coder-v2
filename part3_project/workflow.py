"""
Workflow state machine for a JuprisX project.

NEW -> SCANNING -> NEEDS_FIX -> PLAN_READY -> FIXED -> VALIDATED
    -> READY_TO_BUILD -> BUILDING -> PLAYSTORE_READY
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any


class WorkflowState(Enum):
    NEW = "new"
    SCANNING = "scanning"
    NEEDS_FIX = "needs_fix"
    PLAN_READY = "plan_ready"
    FIXED = "fixed"
    VALIDATED = "validated"
    READY_TO_BUILD = "ready_to_build"
    BUILDING = "building"
    PLAYSTORE_READY = "playstore_ready"


S = WorkflowState

# Allowed transitions. Any state may re-enter SCANNING (re-scan) except
# while a build is running.
ALLOWED: dict[WorkflowState, set[WorkflowState]] = {
    S.NEW: {S.SCANNING},
    S.SCANNING: {S.NEEDS_FIX, S.VALIDATED},          # clean project skips fixing
    S.NEEDS_FIX: {S.PLAN_READY, S.SCANNING},
    S.PLAN_READY: {S.FIXED, S.NEEDS_FIX, S.SCANNING},  # reject -> NEEDS_FIX
    S.FIXED: {S.VALIDATED, S.NEEDS_FIX, S.SCANNING},   # validation failed / rollback
    S.VALIDATED: {S.READY_TO_BUILD, S.NEEDS_FIX, S.SCANNING},
    S.READY_TO_BUILD: {S.BUILDING, S.NEEDS_FIX, S.SCANNING},
    S.BUILDING: {S.PLAYSTORE_READY, S.READY_TO_BUILD},  # failed build -> back
    S.PLAYSTORE_READY: {S.SCANNING, S.BUILDING, S.NEEDS_FIX},
}


class InvalidTransition(ValueError):
    pass


class Workflow:
    def __init__(self, state: WorkflowState | str = WorkflowState.NEW,
                 history: list[dict[str, Any]] | None = None):
        self.current_state = self._coerce(state)
        self.history: list[dict[str, Any]] = list(history or [])

    @staticmethod
    def _coerce(state: WorkflowState | str) -> WorkflowState:
        if isinstance(state, WorkflowState):
            return state
        try:
            return WorkflowState(str(state).lower())
        except ValueError:
            return WorkflowState.NEW

    def can_transition(self, new_state: WorkflowState | str) -> bool:
        new_state = self._coerce(new_state)
        return new_state in ALLOWED.get(self.current_state, set())

    def transition_to(self, new_state: WorkflowState | str, note: str = "") -> WorkflowState:
        new_state = self._coerce(new_state)
        if new_state == self.current_state:
            return self.current_state
        if not self.can_transition(new_state):
            raise InvalidTransition(
                f"Cannot go from {self.current_state.value} to {new_state.value}"
            )
        self.history.append({
            "from": self.current_state.value,
            "to": new_state.value,
            "at": datetime.now().isoformat(timespec="seconds"),
            "note": note,
        })
        self.current_state = new_state
        return self.current_state

    def next_options(self) -> list[str]:
        return sorted(s.value for s in ALLOWED.get(self.current_state, set()))

    @property
    def value(self) -> str:
        return self.current_state.value
