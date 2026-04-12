"""Initial safeguarding schema.

Revision ID: 001
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS safeguarding")

    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bank_name", sa.String(255), nullable=False),
        sa.Column("account_number", sa.String(50), nullable=False),
        sa.Column("sort_code", sa.String(10)),
        sa.Column("iban", sa.String(34)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("account_type", sa.String(20), nullable=False, server_default="segregated"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("acknowledgement_letter_received", sa.Boolean, server_default="false"),
        sa.Column("acknowledgement_date", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        schema="safeguarding",
    )

    op.create_table(
        "positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("position_date", sa.Date, nullable=False, unique=True),
        sa.Column("total_client_funds", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_safeguarded", sa.Numeric(18, 2), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        schema="safeguarding",
    )

    op.create_table(
        "position_details",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("position_id", UUID(as_uuid=True), sa.ForeignKey("safeguarding.positions.id"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("safeguarding.accounts.id"), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_source", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        schema="safeguarding",
    )

    op.create_table(
        "reconciliations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("recon_type", sa.String(10), nullable=False),
        sa.Column("recon_date", sa.Date, nullable=False),
        sa.Column("ledger_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("bank_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("break_items", JSONB, server_default="[]"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        schema="safeguarding",
    )

    op.create_table(
        "breaches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("breach_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("shortfall_amount", sa.Numeric(18, 2)),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("fca_notified", sa.Boolean, server_default="false"),
        sa.Column("fca_notified_at", sa.DateTime(timezone=True)),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("remediation_notes", sa.Text),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
        schema="safeguarding",
    )


def downgrade() -> None:
    op.drop_table("breaches", schema="safeguarding")
    op.drop_table("reconciliations", schema="safeguarding")
    op.drop_table("position_details", schema="safeguarding")
    op.drop_table("positions", schema="safeguarding")
    op.drop_table("accounts", schema="safeguarding")
    op.execute("DROP SCHEMA IF EXISTS safeguarding")
