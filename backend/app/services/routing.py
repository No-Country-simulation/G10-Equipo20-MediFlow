from datetime import UTC, datetime

from app.schemas.processing import ClassificationResult, RoutingResult
from app.services.errors import DocumentError


def route_classification(classification: ClassificationResult) -> RoutingResult:
    if classification.document_type == "DISCHARGE_SUMMARY" and classification.specialty not in ("OTHER", "UNKNOWN"):
        return RoutingResult(destination="HISTORIA_CLINICA", routed_at=datetime.now(UTC), rule_version="discharge-v1")
    destinations = {
        "ECHOCARDIOGRAM_REPORT": "CARDIOLOGIA", "ECG_REPORT": "CARDIOLOGIA",
        "SPIROMETRY_REPORT": "NEUMOLOGIA", "CHEST_IMAGING_REPORT": "NEUMOLOGIA",
    }
    destination = destinations.get(classification.document_type)
    if not destination or classification.specialty in ("OTHER", "UNKNOWN"):
        raise DocumentError(422, "NO_ROUTING_RULE")
    if classification.specialty == "CARDIOPULMONARY":
        destination = "CARDIOPULMONAR"
    return RoutingResult(destination=destination, routed_at=datetime.now(UTC))
