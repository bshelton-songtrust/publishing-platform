"""Musical work models for catalog management."""

from sqlalchemy import (
    Column, String, Integer, Numeric, Text, Boolean, CheckConstraint,
    Index, UniqueConstraint, ForeignKey, Table
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Work(BaseModel):
    """
    Musical work model representing songs, compositions, and musical pieces.
    This is the core entity for catalog management.
    """
    
    __tablename__ = "works"
    
    # Core identification
    title = Column(
        String(500), 
        nullable=False,
        comment="Primary title of the musical work"
    )
    iswc = Column(
        String(15),
        comment="International Standard Musical Work Code (T-XXXXXXXXX-X)"
    )
    
    # Alternate titles for search and identification
    alternate_titles = Column(
        JSONB, 
        default=list,
        comment="Array of alternate titles and working titles"
    )
    
    # Classification
    genre = Column(
        String(100),
        comment="Primary musical genre"
    )
    subgenre = Column(
        String(100),
        comment="Subgenre classification"
    )
    language = Column(
        String(10),
        comment="Primary language (ISO 639-1 code)"
    )
    
    # Technical details
    duration = Column(
        Integer,
        comment="Duration in seconds"
    )
    tempo = Column(
        Integer,
        comment="Tempo in beats per minute (BPM)"
    )
    key_signature = Column(
        String(10),
        comment="Musical key signature (e.g., 'C', 'Am', 'F#')"
    )
    time_signature = Column(
        String(10),
        comment="Time signature (e.g., '4/4', '3/4', '6/8')"
    )
    
    # Registration and status
    registration_status = Column(
        String(20), 
        default="draft",
        nullable=False,
        comment="Work registration status"
    )
    registration_date = Column(
        String, # Using String to handle various date formats during migration
        comment="Date when work was officially registered"
    )
    publication_date = Column(
        String, # Using String to handle various date formats
        comment="Date of first publication"
    )
    
    # Content classification
    is_instrumental = Column(
        Boolean, 
        default=False,
        comment="True if work is purely instrumental"
    )
    has_lyrics = Column(
        Boolean, 
        default=True,
        comment="True if work contains lyrics"
    )
    
    # Rights and ownership info
    rights_society = Column(
        String(100),
        comment="Primary collecting society (PRO)"
    )
    rights_status = Column(
        String(50),
        comment="Current rights administration status"
    )
    
    # Additional metadata
    description = Column(
        Text,
        comment="Detailed description or notes about the work"
    )
    tags = Column(
        JSONB, 
        default=list,
        comment="Array of tags for categorization and search"
    )
    
    # External references
    external_ids = Column(
        JSONB, 
        default=dict,
        comment="External system identifiers (MusicBrainz, etc.)"
    )
    
    # Collaboration and version info
    original_work_id = Column(
        UUID(as_uuid=True),
        ForeignKey("works.id"),
        comment="Reference to original work if this is a derivative"
    )
    version_info = Column(
        JSONB, 
        default=dict,
        comment="Version information for arrangements, adaptations, etc."
    )
    
    # Full-text search
    search_vector = Column(
        TSVECTOR,
        comment="Full-text search vector for titles and content"
    )

    # Relationships
    writers = relationship(
        "WorkWriter", 
        back_populates="work",
        cascade="all, delete-orphan"
    )
    original_work = relationship(
        "Work",
        remote_side="Work.id"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "registration_status IN ('draft', 'pending', 'registered', 'published', 'archived')",
            name="valid_registration_status"
        ),
        CheckConstraint(
            "length(title) > 0",
            name="title_not_empty"
        ),
        CheckConstraint(
            "iswc IS NULL OR iswc ~ '^T-[0-9]{9}-[0-9]$'",
            name="valid_iswc_format"
        ),
        CheckConstraint(
            "language IS NULL OR language ~ '^[a-z]{2}(-[A-Z]{2})?$'",
            name="valid_language_code"
        ),
        CheckConstraint(
            "duration IS NULL OR duration > 0",
            name="positive_duration"
        ),
        CheckConstraint(
            "tempo IS NULL OR (tempo >= 20 AND tempo <= 300)",
            name="reasonable_tempo_range"
        ),
        # Unique constraints
        UniqueConstraint(
            "tenant_id", "iswc",
            name="unique_iswc_per_tenant",
            deferrable=True,
            initially="deferred"
        ),
        # Indexes for performance
        Index("idx_works_tenant_id", "tenant_id"),
        Index("idx_works_title", "title"),
        Index("idx_works_iswc", "iswc"),
        Index("idx_works_genre", "genre"),
        Index("idx_works_language", "language"),
        Index("idx_works_registration_status", "registration_status"),
        Index("idx_works_registration_date", "registration_date"),
        Index("idx_works_search", "search_vector", postgresql_using="gin"),
        Index("idx_works_alternate_titles", "alternate_titles", postgresql_using="gin"),
        Index("idx_works_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Work(id={self.id}, title='{self.title}', iswc='{self.iswc}')>"


class WorkWriter(BaseModel):
    """
    Junction table linking works to songwriters with role and contribution information.
    Represents the creative contributions to a musical work.
    """
    
    __tablename__ = "work_writers"
    
    # Foreign keys
    work_id = Column(
        UUID(as_uuid=True),
        ForeignKey("works.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the musical work"
    )
    songwriter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("songwriters.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the songwriter"
    )
    
    # Role and contribution details
    role = Column(
        String(50), 
        nullable=False,
        comment="Writer role: composer, lyricist, composer_lyricist"
    )
    contribution_percentage = Column(
        Numeric(5, 2),
        comment="Percentage of creative contribution (0.00-100.00)"
    )
    
    # Additional role information
    is_primary = Column(
        Boolean, 
        default=False,
        comment="True if this is the primary writer for this role"
    )
    credit_name = Column(
        String(255),
        comment="Name to use in credits (if different from songwriter name)"
    )
    
    # Rights information
    publishing_share = Column(
        Numeric(5, 2),
        comment="Publishing rights percentage (0.00-100.00)"
    )
    writer_share = Column(
        Numeric(5, 2),
        comment="Writer rights percentage (0.00-100.00)"
    )
    
    # Collaboration details
    contribution_description = Column(
        Text,
        comment="Description of the specific contribution"
    )

    # Relationships
    work = relationship("Work", back_populates="writers")
    songwriter = relationship("Songwriter")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "role IN ('composer', 'lyricist', 'composer_lyricist')",
            name="valid_writer_role"
        ),
        CheckConstraint(
            "contribution_percentage IS NULL OR (contribution_percentage >= 0 AND contribution_percentage <= 100)",
            name="valid_contribution_percentage"
        ),
        CheckConstraint(
            "publishing_share IS NULL OR (publishing_share >= 0 AND publishing_share <= 100)",
            name="valid_publishing_share"
        ),
        CheckConstraint(
            "writer_share IS NULL OR (writer_share >= 0 AND writer_share <= 100)",
            name="valid_writer_share"
        ),
        # Prevent duplicate writer-role combinations per work
        UniqueConstraint(
            "tenant_id", "work_id", "songwriter_id", "role",
            name="unique_work_writer_role",
            deferrable=True,
            initially="deferred"
        ),
        # Indexes
        Index("idx_work_writers_work_id", "work_id"),
        Index("idx_work_writers_songwriter_id", "songwriter_id"),
        Index("idx_work_writers_role", "role"),
        Index("idx_work_writers_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<WorkWriter(work_id={self.work_id}, songwriter_id={self.songwriter_id}, role='{self.role}')>"