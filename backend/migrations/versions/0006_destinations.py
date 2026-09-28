"""Add editable triage destinations and routing rules."""

from alembic import op
import sqlalchemy as sa

revision = "0006_destinations"
down_revision = "0005_readable_storage_key"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("destinations",
                    sa.Column("code", sa.String(60), primary_key=True),
                    sa.Column("name", sa.String(120), nullable=False),
                    sa.Column("kind", sa.String(20), nullable=False),
                    sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("routing_rules",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("document_type", sa.String(50), nullable=False),
                    sa.Column("specialty", sa.String(30), nullable=False),
                    sa.Column("destination_code", sa.String(60), sa.ForeignKey("destinations.code", ondelete="RESTRICT"), nullable=False),
                    sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.UniqueConstraint("document_type", "specialty", name="uq_routing_rule_match"))
    destinations = sa.table("destinations", sa.column("code", sa.String), sa.column("name", sa.String),
                            sa.column("kind", sa.String), sa.column("active", sa.Boolean))
    op.bulk_insert(destinations, [dict(code=code, name=name, kind=kind, active=True) for code, name, kind in (
        ("COLA_URGENCIAS_MEDICAS", "Urgencias Médicas", "QUEUE"),
        ("CARDIOLOGIA", "Cardiología", "DEPARTMENT"),
        ("NEUMOLOGIA", "Neumología", "DEPARTMENT"),
        ("CARDIOPULMONAR", "Cardiopulmonar", "DEPARTMENT"),
        ("DIAGNOSTICO_IMAGENES", "Diagnóstico por Imágenes", "DEPARTMENT"),
        ("LABORATORIO", "Laboratorio", "DEPARTMENT"),
        ("FARMACIA_HOSPITALARIA", "Farmacia Hospitalaria", "DEPARTMENT"),
        ("AUDITORIA_AUTORIZACIONES", "Auditoría de Autorizaciones", "QUEUE"),
        ("HISTORIA_CLINICA", "Historia Clínica Electrónica", "SYSTEM"),
        ("REVISION_HUMANA", "Revisión Humana", "QUEUE"),
    )])
    rules = sa.table("routing_rules", sa.column("document_type", sa.String),
                     sa.column("specialty", sa.String), sa.column("destination_code", sa.String),
                     sa.column("active", sa.Boolean))
    op.bulk_insert(rules, [dict(document_type=doc, specialty=specialty, destination_code=destination, active=True)
                           for doc, specialty, destination in (
        ("ECHOCARDIOGRAM_REPORT", "ANY", "CARDIOLOGIA"),
        ("ECG_REPORT", "ANY", "CARDIOLOGIA"),
        ("SPIROMETRY_REPORT", "ANY", "NEUMOLOGIA"),
        ("CHEST_IMAGING_REPORT", "ANY", "NEUMOLOGIA"),
        ("DISCHARGE_SUMMARY", "ANY", "HISTORIA_CLINICA"),
        ("ECHOCARDIOGRAM_REPORT", "CARDIOPULMONARY", "CARDIOPULMONAR"),
        ("ECG_REPORT", "CARDIOPULMONARY", "CARDIOPULMONAR"),
        ("SPIROMETRY_REPORT", "CARDIOPULMONARY", "CARDIOPULMONAR"),
        ("CHEST_IMAGING_REPORT", "CARDIOPULMONARY", "CARDIOPULMONAR"),
    )])


def downgrade():
    op.drop_table("routing_rules")
    op.drop_table("destinations")
