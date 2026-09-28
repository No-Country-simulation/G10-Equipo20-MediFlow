"""Single-actor local policy, replace with verified identity before multi-user use."""

from fastapi import Depends, HTTPException


def current_actor() -> dict[str, str]:
    return {"id": "superadmin-local", "role": "SUPERADMIN"}


def require_superadmin(actor: dict[str, str] = Depends(current_actor)) -> dict[str, str]:
    if actor.get("role") != "SUPERADMIN":
        raise HTTPException(403, "SUPERADMIN_REQUIRED")
    return actor
