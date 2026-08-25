"""Backfill legacy ownership and canonical snapshot mappings before contract."""

import sqlalchemy as sa
from alembic import op

revision = "0016_backfill_and_constraints"
down_revision = "0015_usage_quota_ledger"
branch_labels = None
depends_on = None

LEGACY_USER = "legacy:system"
LEGACY_ORG = "org_legacy"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO users
                (id, email, display_name, status, created_at, updated_at)
            VALUES
                (:user_id, NULL, 'Legacy data owner', 'active', now(), now())
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(user_id=LEGACY_USER)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO organizations
                (id, name, slug, kind, owner_user_id, status, created_at, updated_at)
            VALUES
                (:org_id, 'Legacy workspace', 'legacy-workspace', 'team',
                 :user_id, 'active', now(), now())
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(org_id=LEGACY_ORG, user_id=LEGACY_USER)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES
                ('mem_legacy_system', :org_id, :user_id, 'owner', 'active', now(), now())
            ON CONFLICT (organization_id, user_id) DO NOTHING
            """
        ).bindparams(org_id=LEGACY_ORG, user_id=LEGACY_USER)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO organization_repositories
                (id, organization_id, repository_id, added_by, visibility,
                 created_at, updated_at)
            SELECT
                'orgrepo_' || substr(md5(id), 1, 24), :org_id, id, :user_id,
                'organization', now(), now()
            FROM repositories
            ON CONFLICT (organization_id, repository_id) DO NOTHING
            """
        ).bindparams(org_id=LEGACY_ORG, user_id=LEGACY_USER)
    )
    for table in ("learner_profiles", "chat_sessions"):
        op.execute(
            sa.text(f"UPDATE {table} SET user_id = :user_id WHERE user_id IS NULL").bindparams(
                user_id=LEGACY_USER
            )
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"
            ).bindparams(org_id=LEGACY_ORG)
        )
    op.execute(
        sa.text("UPDATE deep_tasks SET user_id = :user_id WHERE user_id IS NULL").bindparams(
            user_id=LEGACY_USER
        )
    )
    op.execute(
        sa.text(
            "UPDATE deep_tasks SET organization_id = :org_id WHERE organization_id IS NULL"
        ).bindparams(org_id=LEGACY_ORG)
    )
    op.execute(
        sa.text(
            """
            UPDATE repository_snapshots
            SET analysis_fingerprint = 'legacy:' || md5(
                coalesce(parser_version, '') || ':' ||
                coalesce(index_version, '') || ':' ||
                coalesce(embedding_model, '')
            )
            WHERE analysis_fingerprint IS NULL
            """
        )
    )
    op.create_table(
        "snapshot_canonical_mappings",
        sa.Column(
            "duplicate_snapshot_id",
            sa.String(48),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "canonical_snapshot_id",
            sa.String(48),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    first_value(id) OVER (
                        PARTITION BY repository_id, commit_sha, analysis_fingerprint
                        ORDER BY CASE WHEN status = 'ready' THEN 0 ELSE 1 END, created_at
                    ) AS canonical_id,
                    row_number() OVER (
                        PARTITION BY repository_id, commit_sha, analysis_fingerprint
                        ORDER BY CASE WHEN status = 'ready' THEN 0 ELSE 1 END, created_at
                    ) AS rn
                FROM repository_snapshots
                WHERE commit_sha IS NOT NULL AND analysis_fingerprint IS NOT NULL
            )
            INSERT INTO snapshot_canonical_mappings
                (duplicate_snapshot_id, canonical_snapshot_id)
            SELECT id, canonical_id
            FROM ranked
            WHERE rn > 1
            ON CONFLICT DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE repository_snapshots AS duplicate
            SET analysis_fingerprint = duplicate.analysis_fingerprint ||
                ':duplicate:' || substr(md5(duplicate.id), 1, 12)
            FROM snapshot_canonical_mappings AS mapping
            WHERE mapping.duplicate_snapshot_id = duplicate.id
            """
        )
    )
    op.create_index(
        "uq_snapshot_identity",
        "repository_snapshots",
        ["repository_id", "commit_sha", "analysis_fingerprint"],
        unique=True,
        postgresql_where=sa.text("commit_sha IS NOT NULL AND analysis_fingerprint IS NOT NULL"),
    )
    op.drop_index("ix_snapshot_identity_lookup", table_name="repository_snapshots")


def downgrade() -> None:
    op.create_index(
        "ix_snapshot_identity_lookup",
        "repository_snapshots",
        ["repository_id", "commit_sha", "analysis_fingerprint"],
    )
    op.drop_index("uq_snapshot_identity", table_name="repository_snapshots")
    op.drop_table("snapshot_canonical_mappings")
