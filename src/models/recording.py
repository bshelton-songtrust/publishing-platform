"""Recording models for sound recording management."""

from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, CheckConstraint,
    Index, UniqueConstraint, ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Recording(BaseModel):
    """
    Sound recording model representing specific performances/recordings of musical works.
    Links to the underlying musical work composition.
    """
    
    __tablename__ = "recordings"
    
    # Link to musical work
    work_id = Column(
        UUID(as_uuid=True),
        ForeignKey("works.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the underlying musical work"
    )
    
    # Core identification
    title = Column(
        String(500), 
        nullable=False,
        comment="Recording title (may differ from work title)"
    )
    isrc = Column(
        String(12),
        comment="International Standard Recording Code"
    )
    
    # Artist and performer information
    artist_name = Column(
        String(255), 
        nullable=False,
        comment="Primary performing artist name"
    )
    featured_artists = Column(
        JSONB, 
        default=list,
        comment="Array of featured artist names"
    )
    performer_info = Column(
        JSONB, 
        default=dict,
        comment="Detailed performer information and roles"
    )
    
    # Release information
    album_title = Column(
        String(255),
        comment="Album or release title"
    )
    track_number = Column(
        Integer,
        comment="Track number on the release"
    )
    disc_number = Column(
        Integer,
        comment="Disc number for multi-disc releases"
    )
    
    # Technical specifications
    duration_ms = Column(
        Integer,
        comment="Duration in milliseconds"
    )
    sample_rate = Column(
        Integer,
        comment="Audio sample rate in Hz"
    )
    bit_depth = Column(
        Integer,
        comment="Audio bit depth"
    )
    file_format = Column(
        String(50),
        comment="Audio file format (mp3, wav, flac, etc.)"
    )
    
    # Recording details
    recording_date = Column(
        String, # Using String to handle various date formats
        comment="Date of recording session"
    )
    release_date = Column(
        String, # Using String to handle various date formats  
        comment="Official release date"
    )
    recording_location = Column(
        String(255),
        comment="Studio or location where recorded"
    )
    
    # Commercial and rights information
    label_name = Column(
        String(255),
        comment="Record label name"
    )
    catalog_number = Column(
        String(100),
        comment="Label catalog number"
    )
    upc_ean = Column(
        String(20),
        comment="UPC/EAN barcode for the release"
    )
    
    # Status and classification
    recording_type = Column(
        String(50), 
        default="studio",
        comment="Type of recording: studio, live, demo, remix, etc."
    )
    status = Column(
        String(20), 
        default="active",
        nullable=False,
        comment="Recording status: active, archived, deleted"
    )
    is_master = Column(
        Boolean, 
        default=True,
        comment="True if this is a master recording"
    )
    
    # Content flags
    explicit_content = Column(
        Boolean, 
        default=False,
        comment="True if recording contains explicit content"
    )
    is_cover = Column(
        Boolean, 
        default=False,
        comment="True if this is a cover version"
    )
    is_remix = Column(
        Boolean, 
        default=False,
        comment="True if this is a remix"
    )
    
    # Additional metadata
    description = Column(
        Text,
        comment="Additional notes or description"
    )
    tags = Column(
        JSONB, 
        default=list,
        comment="Tags for categorization and discovery"
    )
    production_credits = Column(
        JSONB, 
        default=dict,
        comment="Producer, engineer, and other production credits"
    )
    
    # External references
    external_ids = Column(
        JSONB, 
        default=dict,
        comment="External system identifiers (Spotify, Apple Music, etc.)"
    )
    
    # File and media information
    media_files = Column(
        JSONB, 
        default=list,
        comment="Array of associated media files and URLs"
    )

    # Relationships
    work = relationship("Work")
    contributors = relationship(
        "RecordingContributor", 
        back_populates="recording",
        cascade="all, delete-orphan"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "length(title) > 0",
            name="recording_title_not_empty"
        ),
        CheckConstraint(
            "isrc IS NULL OR isrc ~ '^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'",
            name="valid_isrc_format"
        ),
        CheckConstraint(
            "recording_type IN ('studio', 'live', 'demo', 'remix', 'remaster', 'alternate', 'acoustic')",
            name="valid_recording_type"
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="valid_recording_status"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms > 0",
            name="positive_duration_ms"
        ),
        CheckConstraint(
            "track_number IS NULL OR track_number > 0",
            name="positive_track_number"
        ),
        CheckConstraint(
            "disc_number IS NULL OR disc_number > 0",
            name="positive_disc_number"
        ),
        # Unique constraints
        UniqueConstraint(
            "tenant_id", "isrc",
            name="unique_isrc_per_tenant",
            deferrable=True,
            initially="deferred"
        ),
        # Indexes for performance
        Index("idx_recordings_tenant_id", "tenant_id"),
        Index("idx_recordings_work_id", "work_id"),
        Index("idx_recordings_title", "title"),
        Index("idx_recordings_isrc", "isrc"),
        Index("idx_recordings_artist_name", "artist_name"),
        Index("idx_recordings_album_title", "album_title"),
        Index("idx_recordings_release_date", "release_date"),
        Index("idx_recordings_status", "status"),
        Index("idx_recordings_recording_type", "recording_type"),
        Index("idx_recordings_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Recording(id={self.id}, title='{self.title}', artist='{self.artist_name}', isrc='{self.isrc}')>"


class RecordingContributor(BaseModel):
    """
    Junction table linking recordings to contributors (performers, producers, etc.).
    Represents various roles in the creation of a sound recording.
    """
    
    __tablename__ = "recording_contributors"
    
    # Foreign keys
    recording_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the recording"
    )
    contributor_name = Column(
        String(255), 
        nullable=False,
        comment="Name of the contributor"
    )
    
    # Role and contribution details
    role = Column(
        String(100), 
        nullable=False,
        comment="Role: vocalist, musician, producer, engineer, etc."
    )
    instrument = Column(
        String(100),
        comment="Specific instrument played (if applicable)"
    )
    
    # Additional information
    is_primary = Column(
        Boolean, 
        default=False,
        comment="True if this is a primary contributor for this role"
    )
    credit_name = Column(
        String(255),
        comment="Name to use in credits (if different)"
    )
    contribution_description = Column(
        Text,
        comment="Detailed description of the contribution"
    )

    # Relationships
    recording = relationship("Recording", back_populates="contributors")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "length(contributor_name) > 0",
            name="contributor_name_not_empty"
        ),
        CheckConstraint(
            "length(role) > 0",
            name="contributor_role_not_empty"
        ),
        # Prevent duplicate contributor-role combinations per recording
        UniqueConstraint(
            "tenant_id", "recording_id", "contributor_name", "role", "instrument",
            name="unique_recording_contributor_role",
            deferrable=True,
            initially="deferred"
        ),
        # Indexes
        Index("idx_recording_contributors_recording_id", "recording_id"),
        Index("idx_recording_contributors_contributor_name", "contributor_name"),
        Index("idx_recording_contributors_role", "role"),
        Index("idx_recording_contributors_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<RecordingContributor(recording_id={self.recording_id}, name='{self.contributor_name}', role='{self.role}')>"