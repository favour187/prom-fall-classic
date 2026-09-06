"""Competition-specific module: event.

Placeholder status router. The real product logic will be added here in the
dedicated build phase for this competition, keeping all competition-specific
code separate from the generic foundation.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/event", tags=["event"])


@router.get("/status")
def feature_status() -> dict:
    return {
        "feature": "event",
        "status": "planned",
        "note": "Placeholder. No competition-specific logic yet: the event's rules, dates and build window could not be verified from public sources.",
    }
