"""Add documentary routes without replacing administrator assignments."""
from alembic import op

revision = "0009_document_contracts"
down_revision = "0008_accounts_laboratory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("INSERT INTO routing_rules (document_type, specialty, destination_code, active) VALUES "
               "('PRESCRIPTION', 'ANY', 'FARMACIA_HOSPITALARIA', true), "
               "('PROCEDURE_ORDER', 'ANY', 'AUDITORIA_AUTORIZACIONES', true), "
               "('MEDICAL_CERTIFICATE', 'ANY', 'HISTORIA_CLINICA', true), "
               "('IMAGING_REPORT', 'ANY', 'HISTORIA_CLINICA', true) "
               "ON CONFLICT (document_type, specialty) DO NOTHING")


def downgrade():
    # Administrative assignments may already have been edited; retain them.
    pass
