"""Local administrative catalog; delivery to external systems is out of scope."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import require_staff, require_permission, same_origin
from app.core.database import get_session
from app.models.destination import Destination, RoutingRule
from app.models.document import Document
from app.core.document_catalog import DocumentType, Specialty as ClassifiedSpecialty

router = APIRouter(tags=["destinations"], dependencies=[Depends(require_staff), Depends(same_origin)])
Db = Annotated[Session, Depends(get_session)]
Admin = Annotated[dict[str, str], Depends(require_staff)]
Specialty = Literal["ANY"] | ClassifiedSpecialty


class DestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,59}$")
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["DEPARTMENT", "QUEUE", "SYSTEM"]


class DestinationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: Literal["DEPARTMENT", "QUEUE", "SYSTEM"] | None = None
    active: bool | None = None


class DestinationOutput(DestinationInput):
    active: bool

    model_config = ConfigDict(from_attributes=True)


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: DocumentType
    specialty: Specialty = "ANY"
    destination_code: str
    active: bool = True

    @field_validator("document_type", "specialty")
    @classmethod
    def supported_type(cls, value):
        if value in ("OTHER", "UNKNOWN"):
            raise ValueError("No se asignan rutas automáticas a tipos desconocidos")
        return value


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_code: str | None = None
    active: bool | None = None


class RuleOutput(RuleInput):
    id: int

    model_config = ConfigDict(from_attributes=True)


def active_destination(session: Session, code: str) -> Destination:
    destination = session.get(Destination, code)
    if destination is None or not destination.active:
        raise HTTPException(422, "DESTINATION_NOT_ACTIVE")
    return destination


@router.get("/destinations", response_model=list[DestinationOutput], dependencies=[Depends(require_permission("DESTINATIONS_READ"))])
def list_destinations(session: Db):
    return session.scalars(select(Destination).order_by(Destination.name)).all()


@router.post("/destinations", response_model=DestinationOutput, status_code=201, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def create_destination(payload: DestinationInput, session: Db, admin: Admin):
    destination = Destination(**payload.model_dump(), active=True)
    session.add(destination)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "DESTINATION_EXISTS") from None
    return destination


@router.patch("/destinations/{code}", response_model=DestinationOutput, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def update_destination(code: str, payload: DestinationUpdate, session: Db, admin: Admin):
    destination = session.get(Destination, code)
    if destination is None:
        raise HTTPException(404, "DESTINATION_NOT_FOUND")
    if payload.active is False:
        if code == "COLA_URGENCIAS_MEDICAS":
            raise HTTPException(409, "URGENT_DESTINATION_REQUIRED")
        assigned = session.scalar(select(func.count()).select_from(RoutingRule).where(
            RoutingRule.destination_code == code, RoutingRule.active.is_(True)))
        if assigned:
            raise HTTPException(409, "DESTINATION_HAS_ACTIVE_RULES")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(destination, key, value)
    session.commit()
    return destination


@router.delete("/destinations/{code}", status_code=204, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def delete_destination(code: str, session: Db, admin: Admin):
    destination = session.get(Destination, code)
    if destination is None:
        raise HTTPException(404, "DESTINATION_NOT_FOUND")
    if code == "COLA_URGENCIAS_MEDICAS":
        raise HTTPException(409, "URGENT_DESTINATION_REQUIRED")
    if session.scalar(select(func.count()).select_from(RoutingRule).where(RoutingRule.destination_code == code)):
        raise HTTPException(409, "DESTINATION_HAS_RULES")
    if session.scalar(select(func.count()).select_from(Document).where(
        Document.processing_result["routing"]["destination"].astext == code)):
        raise HTTPException(409, "DESTINATION_HAS_HISTORY")
    session.delete(destination)
    session.commit()
    return Response(status_code=204)


@router.get("/routing-rules", response_model=list[RuleOutput], dependencies=[Depends(require_permission("DESTINATIONS_READ"))])
def list_rules(session: Db):
    return session.scalars(select(RoutingRule).order_by(RoutingRule.document_type,
                                                        RoutingRule.specialty)).all()


@router.post("/routing-rules", response_model=RuleOutput, status_code=201, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def create_rule(payload: RuleInput, session: Db, admin: Admin):
    active_destination(session, payload.destination_code)
    rule = RoutingRule(**payload.model_dump())
    session.add(rule)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "ROUTING_RULE_EXISTS") from None
    return rule


@router.patch("/routing-rules/{rule_id}", response_model=RuleOutput, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def update_rule(rule_id: int, payload: RuleUpdate, session: Db, admin: Admin):
    rule = session.get(RoutingRule, rule_id)
    if rule is None:
        raise HTTPException(404, "ROUTING_RULE_NOT_FOUND")
    if payload.destination_code is not None:
        active_destination(session, payload.destination_code)
        rule.destination_code = payload.destination_code
    if payload.active is not None:
        if payload.active:
            active_destination(session, rule.destination_code)
        rule.active = payload.active
    session.commit()
    return rule


@router.delete("/routing-rules/{rule_id}", status_code=204, dependencies=[Depends(require_permission("DESTINATIONS_MANAGE"))])
def delete_rule(rule_id: int, session: Db, admin: Admin):
    rule = session.get(RoutingRule, rule_id)
    if rule is None:
        raise HTTPException(404, "ROUTING_RULE_NOT_FOUND")
    session.delete(rule)
    session.commit()
    return Response(status_code=204)
