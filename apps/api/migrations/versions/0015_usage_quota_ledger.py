"""Add plans, quota periods, reservations, append-only usage and audit ledger."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_usage_quota_ledger"
down_revision = "0014_semantic_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column(
            "monthly_allowance_micro_usd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "policy_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plan_id", sa.String(48), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "quota_periods",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allowance_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("reserved_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("consumed_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bonus_consumed_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_quota_org_period", "quota_periods", ["organization_id", "period_start"], unique=True
    )
    op.create_table(
        "feature_limits",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "plan_id", sa.String(48), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("request_limit", sa.Integer()),
        sa.Column("token_limit", sa.BigInteger()),
        sa.Column("duration_limit_seconds", sa.Integer()),
        sa.Column("concurrent_limit", sa.Integer()),
        sa.Column("max_input_size", sa.Integer()),
        sa.Column("max_output_tokens", sa.Integer()),
    )
    op.create_index(
        "uq_feature_limit_plan_feature", "feature_limits", ["plan_id", "feature"], unique=True
    )
    op.create_table(
        "bonus_credit_grants",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("remaining_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(240), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "usage_reservations",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "quota_period_id",
            sa.String(48),
            sa.ForeignKey("quota_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("estimated_cost_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("settled_cost_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("provider_request_id", sa.String(160)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_usage_reservation_idempotency",
        "usage_reservations",
        ["organization_id", "idempotency_key"],
        unique=True,
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "reservation_id",
            sa.String(48),
            sa.ForeignKey("usage_reservations.id", ondelete="SET NULL"),
        ),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("provider", sa.String(40)),
        sa.Column("model", sa.String(120)),
        sa.Column("price_version", sa.String(80)),
        sa.Column("usage_json", postgresql.JSONB(), nullable=False),
        sa.Column("estimated_cost_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("settled_cost_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("cache_status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_usage_event_idempotency",
        "usage_events",
        ["organization_id", "idempotency_key"],
        unique=True,
    )
    op.create_table(
        "model_prices",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("usage_type", sa.String(60), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("micro_usd_per_unit", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_model_price_version",
        "model_prices",
        ["provider", "model", "usage_type", "effective_at"],
        unique=True,
    )
    op.create_table(
        "usage_daily_rollups",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("cache_hit_count", sa.Integer(), nullable=False),
        sa.Column("usage_json", postgresql.JSONB(), nullable=False),
        sa.Column("settled_cost_micro_usd", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "uq_usage_rollup_key",
        "usage_daily_rollups",
        ["organization_id", "day", "feature", "provider", "model"],
        unique=True,
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id", sa.String(48), sa.ForeignKey("organizations.id", ondelete="SET NULL")
        ),
        sa.Column("actor_user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    for table in (
        "audit_events",
        "usage_daily_rollups",
        "model_prices",
        "usage_events",
        "usage_reservations",
        "bonus_credit_grants",
        "feature_limits",
        "quota_periods",
        "organization_subscriptions",
        "plans",
    ):
        op.drop_table(table)
