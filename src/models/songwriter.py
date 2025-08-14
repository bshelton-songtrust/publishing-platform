"""Songwriter model for managing music creators."""

from sqlalchemy import (
    Column, String, Date, CheckConstraint, Index, 
    UniqueConstraint, Text, Computed
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from .base import BaseModel


class Songwriter(BaseModel):
    """
    Songwriter model representing music creators and writers.
    Contains personal and professional information for publishing purposes.
    """
    
    __tablename__ = "songwriters"
    
    # Personal information
    first_name = Column(
        String(100), 
        nullable=False,
        comment="Writer's first name"
    )
    last_name = Column(
        String(100), 
        nullable=False,
        comment="Writer's last name"
    )
    full_name = Column(
        String(255),
        Computed("first_name || ' ' || last_name"),
        comment="Computed full name"
    )
    stage_name = Column(
        String(255),
        comment="Professional/stage name"
    )
    
    # Industry identifiers
    ipi = Column(
        String(15),
        comment="Interested Party Information number"
    )
    isni = Column(
        String(16),
        comment="International Standard Name Identifier"
    )
    
    # Contact information
    email = Column(
        String(255),
        comment="Primary email address"
    )
    phone = Column(
        String(50),
        comment="Primary phone number"
    )
    
    # Address information (stored as JSON)
    address = Column(
        JSONB, 
        default=dict,
        comment="Address information: street, city, state, country, postal_code"
    )
    
    # Personal details
    birth_date = Column(
        Date,
        comment="Date of birth"
    )
    birth_country = Column(
        String(2),
        comment="Country of birth (ISO 3166-1 alpha-2)"
    )
    nationality = Column(
        String(2),
        comment="Nationality (ISO 3166-1 alpha-2)"
    )
    gender = Column(
        String(20),
        comment="Gender identity"
    )
    
    # Professional status
    status = Column(
        String(20), 
        default="active",
        nullable=False,
        comment="Writer status: active, inactive, deceased"
    )
    deceased_date = Column(
        Date,
        comment="Date of death (if applicable)"
    )
    
    # Biography and additional information
    biography = Column(
        Text,
        comment="Writer biography or description"
    )
    website = Column(
        String(255),
        comment="Official website URL"
    )
    social_media = Column(
        JSONB, 
        default=dict,
        comment="Social media profiles and handles"
    )
    
    # Full-text search
    search_vector = Column(
        TSVECTOR,
        comment="Full-text search vector"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'deceased')",
            name="valid_songwriter_status"
        ),
        CheckConstraint(
            "birth_country IS NULL OR length(birth_country) = 2",
            name="valid_birth_country_code"
        ),
        CheckConstraint(
            "nationality IS NULL OR length(nationality) = 2", 
            name="valid_nationality_code"
        ),
        CheckConstraint(
            "deceased_date IS NULL OR status = 'deceased'",
            name="deceased_date_requires_deceased_status"
        ),
        # Unique constraints per tenant
        UniqueConstraint(
            "tenant_id", "ipi",
            name="unique_ipi_per_tenant",
            deferrable=True,
            initially="deferred"
        ),
        UniqueConstraint(
            "tenant_id", "email",
            name="unique_email_per_tenant", 
            deferrable=True,
            initially="deferred"
        ),
        # Indexes for common queries
        Index("idx_songwriters_tenant_id", "tenant_id"),
        Index("idx_songwriters_full_name", "full_name"),
        Index("idx_songwriters_stage_name", "stage_name"),
        Index("idx_songwriters_ipi", "ipi"),
        Index("idx_songwriters_isni", "isni"),
        Index("idx_songwriters_email", "email"),
        Index("idx_songwriters_status", "status"),
        Index("idx_songwriters_search", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        display_name = self.stage_name or self.full_name
        return f"<Songwriter(id={self.id}, name='{display_name}')>"