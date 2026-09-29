from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.destination import Destination, RoutingRule
from app.schemas.processing import ClassificationResult, PriorityResult, RoutingResult
from app.services.errors import DocumentError


def route_classification(classification: ClassificationResult, priority: PriorityResult | None = None,
                         session: Session | None = None) -> RoutingResult:
    if session is not None:
        if priority and priority.level in ("URGENT", "CRITICAL"):
            destination = session.get(Destination, "COLA_URGENCIAS_MEDICAS")
            if destination is None or not destination.active:
                raise DocumentError(422, "NO_ROUTING_RULE")
            return RoutingResult(destination=destination.code, routed_at=datetime.now(UTC),
                                 rule_version="explicit-priority-v1")
        if classification.specialty in ("OTHER", "UNKNOWN"):
            raise DocumentError(422, "NO_ROUTING_RULE")
        rules = session.scalars(select(RoutingRule).join(Destination).where(
            RoutingRule.document_type == classification.document_type,
            RoutingRule.specialty.in_((classification.specialty, "ANY")),
            RoutingRule.active.is_(True), Destination.active.is_(True),
        )).all()
        if rules:
            rule = sorted(rules, key=lambda item: item.specialty != classification.specialty)[0]
            return RoutingResult(destination=rule.destination_code, routed_at=datetime.now(UTC),
                                 rule_version="catalog-v1")
        raise DocumentError(422, "NO_ROUTING_RULE")
    if priority and priority.level in ("URGENT", "CRITICAL"):
        return RoutingResult(destination="COLA_URGENCIAS_MEDICAS", routed_at=datetime.now(UTC),
                             rule_version="explicit-priority-v1")
    if classification.document_type == "DISCHARGE_SUMMARY" and classification.specialty not in ("OTHER", "UNKNOWN"):
        return RoutingResult(destination="HISTORIA_CLINICA", routed_at=datetime.now(UTC), rule_version="discharge-v1")
    destinations = {
        "ECHOCARDIOGRAM_REPORT": "CARDIOLOGIA", "ECG_REPORT": "CARDIOLOGIA",
        "SPIROMETRY_REPORT": "NEUMOLOGIA", "CHEST_IMAGING_REPORT": "NEUMOLOGIA",
        "LABORATORY_ORDER": "LABORATORIO", "LABORATORY_RESULT": "HISTORIA_CLINICA",
    }
    destination = destinations.get(classification.document_type)
    if not destination or classification.specialty in ("OTHER", "UNKNOWN"):
        raise DocumentError(422, "NO_ROUTING_RULE")
    if classification.specialty == "CARDIOPULMONARY":
        destination = "CARDIOPULMONAR"
    return RoutingResult(destination=destination, routed_at=datetime.now(UTC))
