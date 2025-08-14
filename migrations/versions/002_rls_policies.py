"""Add Row-Level Security policies for multi-tenant isolation

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable Row-Level Security on all tables
    tables = [
        "tenants", 
        "songwriters", 
        "works", 
        "work_writers", 
        "recordings", 
        "recording_contributors"
    ]
    
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    
    # Create RLS policies for each table
    
    # Tenants table policy - users can only access their own tenant
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON tenants
        FOR ALL TO catalog_service_role
        USING (id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Songwriters table policy
    op.execute("""
        CREATE POLICY songwriters_tenant_isolation ON songwriters
        FOR ALL TO catalog_service_role
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Works table policy
    op.execute("""
        CREATE POLICY works_tenant_isolation ON works
        FOR ALL TO catalog_service_role
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Work writers table policy
    op.execute("""
        CREATE POLICY work_writers_tenant_isolation ON work_writers
        FOR ALL TO catalog_service_role
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Recordings table policy
    op.execute("""
        CREATE POLICY recordings_tenant_isolation ON recordings
        FOR ALL TO catalog_service_role
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Recording contributors table policy
    op.execute("""
        CREATE POLICY recording_contributors_tenant_isolation ON recording_contributors
        FOR ALL TO catalog_service_role
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
    """)
    
    # Grant necessary permissions to the catalog_service_role
    for table in tables:
        op.execute(f"GRANT ALL ON {table} TO catalog_service_role")
    
    # Create function to help with search vector updates
    op.execute("""
        CREATE OR REPLACE FUNCTION update_search_vector_songwriters()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector = to_tsvector('english', 
                COALESCE(NEW.first_name, '') || ' ' ||
                COALESCE(NEW.last_name, '') || ' ' ||
                COALESCE(NEW.stage_name, '') || ' ' ||
                COALESCE(NEW.biography, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create trigger for songwriters search vector
    op.execute("""
        CREATE TRIGGER songwriters_search_vector_update
        BEFORE INSERT OR UPDATE ON songwriters
        FOR EACH ROW EXECUTE FUNCTION update_search_vector_songwriters();
    """)
    
    # Create function for works search vector
    op.execute("""
        CREATE OR REPLACE FUNCTION update_search_vector_works()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector = to_tsvector('english', 
                COALESCE(NEW.title, '') || ' ' ||
                COALESCE(NEW.description, '') || ' ' ||
                COALESCE(array_to_string(NEW.alternate_titles::text[], ' '), '') || ' ' ||
                COALESCE(array_to_string(NEW.tags::text[], ' '), '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create trigger for works search vector
    op.execute("""
        CREATE TRIGGER works_search_vector_update
        BEFORE INSERT OR UPDATE ON works
        FOR EACH ROW EXECUTE FUNCTION update_search_vector_works();
    """)
    
    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create updated_at triggers for all tables
    for table in tables:
        op.execute(f"""
            CREATE TRIGGER {table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    tables = [
        "tenants", 
        "songwriters", 
        "works", 
        "work_writers", 
        "recordings", 
        "recording_contributors"
    ]
    
    for table in tables:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_updated_at ON {table}")
    
    op.execute("DROP TRIGGER IF EXISTS songwriters_search_vector_update ON songwriters")
    op.execute("DROP TRIGGER IF EXISTS works_search_vector_update ON works")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.execute("DROP FUNCTION IF EXISTS update_search_vector_songwriters()")
    op.execute("DROP FUNCTION IF EXISTS update_search_vector_works()")
    
    # Drop RLS policies
    policy_names = [
        ("tenants", "tenant_isolation_policy"),
        ("songwriters", "songwriters_tenant_isolation"),
        ("works", "works_tenant_isolation"),
        ("work_writers", "work_writers_tenant_isolation"),
        ("recordings", "recordings_tenant_isolation"),
        ("recording_contributors", "recording_contributors_tenant_isolation"),
    ]
    
    for table, policy in policy_names:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    
    # Disable RLS
    for table in tables:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")