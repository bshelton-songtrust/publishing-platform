"""Initial schema with multi-tenant tables and Row-Level Security

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\"")
    
    # Create application role for Row-Level Security
    op.execute("DO $$ BEGIN CREATE ROLE catalog_service_role; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    
    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subdomain", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column("plan_type", sa.String(50), nullable=False, default="free"),
        sa.Column("settings", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.UniqueConstraint("subdomain"),
        sa.CheckConstraint("status IN ('active', 'suspended', 'archived', 'trial')", name="valid_tenant_status"),
        sa.CheckConstraint("plan_type IN ('free', 'starter', 'professional', 'enterprise')", name="valid_plan_type"),
    )
    
    # Create indexes for tenants
    op.create_index("idx_tenants_subdomain", "tenants", ["subdomain"])
    op.create_index("idx_tenants_status", "tenants", ["status"])
    
    # Create songwriters table
    op.create_table(
        "songwriters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("full_name", sa.String(255), sa.Computed("first_name || ' ' || last_name")),
        sa.Column("stage_name", sa.String(255)),
        sa.Column("ipi", sa.String(15)),
        sa.Column("isni", sa.String(16)),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("address", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("birth_date", sa.Date),
        sa.Column("birth_country", sa.String(2)),
        sa.Column("nationality", sa.String(2)),
        sa.Column("gender", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column("deceased_date", sa.Date),
        sa.Column("biography", sa.Text),
        sa.Column("website", sa.String(255)),
        sa.Column("social_media", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", postgresql.TSVECTOR),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'deceased')", name="valid_songwriter_status"),
        sa.CheckConstraint("birth_country IS NULL OR length(birth_country) = 2", name="valid_birth_country_code"),
        sa.CheckConstraint("nationality IS NULL OR length(nationality) = 2", name="valid_nationality_code"),
        sa.CheckConstraint("deceased_date IS NULL OR status = 'deceased'", name="deceased_date_requires_deceased_status"),
        sa.UniqueConstraint("tenant_id", "ipi", name="unique_ipi_per_tenant", deferrable=True, initially="deferred"),
        sa.UniqueConstraint("tenant_id", "email", name="unique_email_per_tenant", deferrable=True, initially="deferred"),
    )
    
    # Create indexes for songwriters
    op.create_index("idx_songwriters_tenant_id", "songwriters", ["tenant_id"])
    op.create_index("idx_songwriters_full_name", "songwriters", ["full_name"])
    op.create_index("idx_songwriters_stage_name", "songwriters", ["stage_name"])
    op.create_index("idx_songwriters_ipi", "songwriters", ["ipi"])
    op.create_index("idx_songwriters_isni", "songwriters", ["isni"])
    op.create_index("idx_songwriters_email", "songwriters", ["email"])
    op.create_index("idx_songwriters_status", "songwriters", ["status"])
    op.create_index("idx_songwriters_search", "songwriters", ["search_vector"], postgresql_using="gin")
    
    # Create works table
    op.create_table(
        "works",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("iswc", sa.String(15)),
        sa.Column("alternate_titles", postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column("genre", sa.String(100)),
        sa.Column("subgenre", sa.String(100)),
        sa.Column("language", sa.String(10)),
        sa.Column("duration", sa.Integer),
        sa.Column("tempo", sa.Integer),
        sa.Column("key_signature", sa.String(10)),
        sa.Column("time_signature", sa.String(10)),
        sa.Column("registration_status", sa.String(20), nullable=False, default="draft"),
        sa.Column("registration_date", sa.String),
        sa.Column("publication_date", sa.String),
        sa.Column("is_instrumental", sa.Boolean, default=False),
        sa.Column("has_lyrics", sa.Boolean, default=True),
        sa.Column("rights_society", sa.String(100)),
        sa.Column("rights_status", sa.String(50)),
        sa.Column("description", sa.Text),
        sa.Column("tags", postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column("external_ids", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("original_work_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version_info", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", postgresql.TSVECTOR),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["original_work_id"], ["works.id"]),
        sa.CheckConstraint("registration_status IN ('draft', 'pending', 'registered', 'published', 'archived')", name="valid_registration_status"),
        sa.CheckConstraint("length(title) > 0", name="title_not_empty"),
        sa.CheckConstraint("iswc IS NULL OR iswc ~ '^T-[0-9]{9}-[0-9]$'", name="valid_iswc_format"),
        sa.CheckConstraint("language IS NULL OR language ~ '^[a-z]{2}(-[A-Z]{2})?$'", name="valid_language_code"),
        sa.CheckConstraint("duration IS NULL OR duration > 0", name="positive_duration"),
        sa.CheckConstraint("tempo IS NULL OR (tempo >= 20 AND tempo <= 300)", name="reasonable_tempo_range"),
        sa.UniqueConstraint("tenant_id", "iswc", name="unique_iswc_per_tenant", deferrable=True, initially="deferred"),
    )
    
    # Create indexes for works
    op.create_index("idx_works_tenant_id", "works", ["tenant_id"])
    op.create_index("idx_works_title", "works", ["title"])
    op.create_index("idx_works_iswc", "works", ["iswc"])
    op.create_index("idx_works_genre", "works", ["genre"])
    op.create_index("idx_works_language", "works", ["language"])
    op.create_index("idx_works_registration_status", "works", ["registration_status"])
    op.create_index("idx_works_registration_date", "works", ["registration_date"])
    op.create_index("idx_works_search", "works", ["search_vector"], postgresql_using="gin")
    op.create_index("idx_works_alternate_titles", "works", ["alternate_titles"], postgresql_using="gin")
    op.create_index("idx_works_tags", "works", ["tags"], postgresql_using="gin")
    
    # Create work_writers table
    op.create_table(
        "work_writers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("songwriter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("contribution_percentage", sa.Numeric(5, 2)),
        sa.Column("is_primary", sa.Boolean, default=False),
        sa.Column("credit_name", sa.String(255)),
        sa.Column("publishing_share", sa.Numeric(5, 2)),
        sa.Column("writer_share", sa.Numeric(5, 2)),
        sa.Column("contribution_description", sa.Text),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["songwriter_id"], ["songwriters.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('composer', 'lyricist', 'composer_lyricist')", name="valid_writer_role"),
        sa.CheckConstraint("contribution_percentage IS NULL OR (contribution_percentage >= 0 AND contribution_percentage <= 100)", name="valid_contribution_percentage"),
        sa.CheckConstraint("publishing_share IS NULL OR (publishing_share >= 0 AND publishing_share <= 100)", name="valid_publishing_share"),
        sa.CheckConstraint("writer_share IS NULL OR (writer_share >= 0 AND writer_share <= 100)", name="valid_writer_share"),
        sa.UniqueConstraint("tenant_id", "work_id", "songwriter_id", "role", name="unique_work_writer_role", deferrable=True, initially="deferred"),
    )
    
    # Create indexes for work_writers
    op.create_index("idx_work_writers_work_id", "work_writers", ["work_id"])
    op.create_index("idx_work_writers_songwriter_id", "work_writers", ["songwriter_id"])
    op.create_index("idx_work_writers_role", "work_writers", ["role"])
    op.create_index("idx_work_writers_tenant_id", "work_writers", ["tenant_id"])
    
    # Create recordings table
    op.create_table(
        "recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("isrc", sa.String(12)),
        sa.Column("artist_name", sa.String(255), nullable=False),
        sa.Column("featured_artists", postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column("performer_info", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("album_title", sa.String(255)),
        sa.Column("track_number", sa.Integer),
        sa.Column("disc_number", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("sample_rate", sa.Integer),
        sa.Column("bit_depth", sa.Integer),
        sa.Column("file_format", sa.String(50)),
        sa.Column("recording_date", sa.String),
        sa.Column("release_date", sa.String),
        sa.Column("recording_location", sa.String(255)),
        sa.Column("label_name", sa.String(255)),
        sa.Column("catalog_number", sa.String(100)),
        sa.Column("upc_ean", sa.String(20)),
        sa.Column("recording_type", sa.String(50), default="studio"),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column("is_master", sa.Boolean, default=True),
        sa.Column("explicit_content", sa.Boolean, default=False),
        sa.Column("is_cover", sa.Boolean, default=False),
        sa.Column("is_remix", sa.Boolean, default=False),
        sa.Column("description", sa.Text),
        sa.Column("tags", postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column("production_credits", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("external_ids", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("media_files", postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.CheckConstraint("length(title) > 0", name="recording_title_not_empty"),
        sa.CheckConstraint("isrc IS NULL OR isrc ~ '^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'", name="valid_isrc_format"),
        sa.CheckConstraint("recording_type IN ('studio', 'live', 'demo', 'remix', 'remaster', 'alternate', 'acoustic')", name="valid_recording_type"),
        sa.CheckConstraint("status IN ('active', 'archived', 'deleted')", name="valid_recording_status"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="positive_duration_ms"),
        sa.CheckConstraint("track_number IS NULL OR track_number > 0", name="positive_track_number"),
        sa.CheckConstraint("disc_number IS NULL OR disc_number > 0", name="positive_disc_number"),
        sa.UniqueConstraint("tenant_id", "isrc", name="unique_isrc_per_tenant", deferrable=True, initially="deferred"),
    )
    
    # Create indexes for recordings
    op.create_index("idx_recordings_tenant_id", "recordings", ["tenant_id"])
    op.create_index("idx_recordings_work_id", "recordings", ["work_id"])
    op.create_index("idx_recordings_title", "recordings", ["title"])
    op.create_index("idx_recordings_isrc", "recordings", ["isrc"])
    op.create_index("idx_recordings_artist_name", "recordings", ["artist_name"])
    op.create_index("idx_recordings_album_title", "recordings", ["album_title"])
    op.create_index("idx_recordings_release_date", "recordings", ["release_date"])
    op.create_index("idx_recordings_status", "recordings", ["status"])
    op.create_index("idx_recordings_recording_type", "recordings", ["recording_type"])
    op.create_index("idx_recordings_tags", "recordings", ["tags"], postgresql_using="gin")
    
    # Create recording_contributors table
    op.create_table(
        "recording_contributors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contributor_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=False),
        sa.Column("instrument", sa.String(100)),
        sa.Column("is_primary", sa.Boolean, default=False),
        sa.Column("credit_name", sa.String(255)),
        sa.Column("contribution_description", sa.Text),
        sa.Column("additional_data", postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="CASCADE"),
        sa.CheckConstraint("length(contributor_name) > 0", name="contributor_name_not_empty"),
        sa.CheckConstraint("length(role) > 0", name="contributor_role_not_empty"),
        sa.UniqueConstraint("tenant_id", "recording_id", "contributor_name", "role", "instrument", name="unique_recording_contributor_role", deferrable=True, initially="deferred"),
    )
    
    # Create indexes for recording_contributors
    op.create_index("idx_recording_contributors_recording_id", "recording_contributors", ["recording_id"])
    op.create_index("idx_recording_contributors_contributor_name", "recording_contributors", ["contributor_name"])
    op.create_index("idx_recording_contributors_role", "recording_contributors", ["role"])
    op.create_index("idx_recording_contributors_tenant_id", "recording_contributors", ["tenant_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("recording_contributors")
    op.drop_table("recordings")
    op.drop_table("work_writers")
    op.drop_table("works")
    op.drop_table("songwriters")
    op.drop_table("tenants")
    
    # Drop role
    op.execute("DROP ROLE IF EXISTS catalog_service_role")