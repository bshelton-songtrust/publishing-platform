"""Business rules and validation logic for catalog management."""

from typing import List, Dict, Any, Optional
from uuid import UUID
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ValidationError:
    """Validation error."""
    field: str
    code: str
    message: str


@dataclass 
class ValidationResult:
    """Validation result."""
    is_valid: bool
    errors: List[ValidationError]


@dataclass
class TenantContext:
    """Tenant context for business rule validation."""
    tenant_id: UUID
    plan_type: str
    settings: Dict[str, Any]


class WorkValidator:
    """Work validation rules."""
    
    def validate_work_creation(self, work_data: dict, tenant_context: dict) -> ValidationResult:
        """Validate work creation request."""
        errors = []
        
        # Title validation
        if not work_data.get("title") or len(work_data["title"].strip()) == 0:
            errors.append(ValidationError(
                field="title",
                code="TITLE_REQUIRED",
                message="Work title is required"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class RecordingValidator:
    """Recording validation rules."""
    
    def validate_recording_creation(self, recording_data: dict, tenant_context: dict) -> ValidationResult:
        """Validate recording creation request."""
        errors = []
        
        # Title validation
        if not recording_data.get("title") or len(recording_data["title"].strip()) == 0:
            errors.append(ValidationError(
                field="title",
                code="TITLE_REQUIRED",
                message="Recording title is required"
            ))
            
        # Work ID validation  
        if not recording_data.get("work_id"):
            errors.append(ValidationError(
                field="work_id",
                code="WORK_ID_REQUIRED",
                message="Work ID is required"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class WorkRegistrationRules:
    """Business rules for musical work registration."""
    
    @staticmethod
    def validate_work_creation(work_data: dict, tenant_context: TenantContext) -> ValidationResult:
        """Validate work creation request."""
        errors = []
        
        # Title validation
        if not work_data.get("title") or len(work_data["title"].strip()) == 0:
            errors.append(ValidationError(
                field="title",
                code="TITLE_REQUIRED",
                message="Work title is required"
            ))
        
        if len(work_data.get("title", "")) > 500:
            errors.append(ValidationError(
                field="title",
                code="TITLE_TOO_LONG",
                message="Title cannot exceed 500 characters"
            ))
        
        # ISWC validation (if provided)
        if "iswc" in work_data and work_data["iswc"]:
            iswc_errors = ISWCValidator.validate(work_data["iswc"])
            errors.extend(iswc_errors)
        
        # Language validation
        if "language" in work_data and work_data["language"]:
            lang_errors = LanguageValidator.validate(work_data["language"])
            errors.extend(lang_errors)
        
        # Duration validation
        if "duration" in work_data and work_data["duration"] is not None:
            duration = work_data["duration"]
            if duration <= 0:
                errors.append(ValidationError(
                    field="duration",
                    code="INVALID_DURATION",
                    message="Duration must be positive"
                ))
            if duration > 86400:  # 24 hours max
                errors.append(ValidationError(
                    field="duration",
                    code="DURATION_TOO_LONG",
                    message="Duration cannot exceed 24 hours"
                ))
        
        # Tempo validation
        if "tempo" in work_data and work_data["tempo"] is not None:
            tempo = work_data["tempo"]
            if tempo < 20 or tempo > 300:
                errors.append(ValidationError(
                    field="tempo",
                    code="INVALID_TEMPO",
                    message="Tempo must be between 20 and 300 BPM"
                ))
        
        # Writers validation
        if "writers" in work_data:
            writer_errors = WorkWriterValidator.validate_writers(
                work_data["writers"], tenant_context
            )
            errors.extend(writer_errors)
        
        # Alternate titles validation
        if "alternate_titles" in work_data:
            alt_titles = work_data["alternate_titles"]
            if isinstance(alt_titles, list):
                for i, title in enumerate(alt_titles):
                    if not isinstance(title, str) or len(title.strip()) == 0:
                        errors.append(ValidationError(
                            field=f"alternate_titles[{i}]",
                            code="INVALID_ALTERNATE_TITLE",
                            message="Alternate title must be a non-empty string"
                        ))
        
        # Genre validation
        genre = work_data.get("genre")
        if genre and len(genre) > 100:
            errors.append(ValidationError(
                field="genre",
                code="GENRE_TOO_LONG",
                message="Genre cannot exceed 100 characters"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    @staticmethod
    def validate_work_update(
        work_id: str, 
        work_data: dict, 
        existing_work: dict, 
        tenant_context: TenantContext
    ) -> ValidationResult:
        """Validate work update request."""
        errors = []
        
        # Check if work is in a state that allows updates
        registration_status = existing_work.get("registration_status", "draft")
        
        if registration_status == "registered":
            # Registered works have restricted fields that can be updated
            restricted_fields = ["title", "writers", "iswc"]
            for field in restricted_fields:
                if (field in work_data and 
                    existing_work.get(field) != work_data[field]):
                    errors.append(ValidationError(
                        field=field,
                        code="FIELD_LOCKED",
                        message=f"Cannot modify {field} of registered work"
                    ))
        
        # Apply creation validation rules to the update data
        creation_result = WorkRegistrationRules.validate_work_creation(work_data, tenant_context)
        errors.extend(creation_result.errors)
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class WorkWriterValidator:
    """Validates work-writer relationships."""
    
    @staticmethod
    def validate_writers(writers_data: List[dict], tenant_context: TenantContext) -> List[ValidationError]:
        """Validate writers array."""
        errors = []
        
        if not writers_data or len(writers_data) == 0:
            errors.append(ValidationError(
                field="writers",
                code="NO_WRITERS",
                message="Work must have at least one writer"
            ))
            return errors
        
        total_contribution = Decimal("0")
        roles_seen = set()
        songwriter_ids_seen = set()
        
        for i, writer in enumerate(writers_data):
            field_prefix = f"writers[{i}]"
            
            # Required fields
            if "songwriter_id" not in writer or not writer["songwriter_id"]:
                errors.append(ValidationError(
                    field=f"{field_prefix}.songwriter_id",
                    code="SONGWRITER_ID_REQUIRED",
                    message="Songwriter ID is required"
                ))
            else:
                # Check for duplicate songwriter in different roles
                songwriter_id = str(writer["songwriter_id"])
                role = writer.get("role", "")
                songwriter_role_key = f"{songwriter_id}:{role}"
                
                if songwriter_role_key in songwriter_ids_seen:
                    errors.append(ValidationError(
                        field=f"{field_prefix}.songwriter_id",
                        code="DUPLICATE_SONGWRITER_ROLE",
                        message=f"Songwriter already assigned to role '{role}'"
                    ))
                songwriter_ids_seen.add(songwriter_role_key)
            
            # Role validation
            if "role" not in writer or not writer["role"]:
                errors.append(ValidationError(
                    field=f"{field_prefix}.role",
                    code="ROLE_REQUIRED",
                    message="Writer role is required"
                ))
            else:
                role = writer["role"]
                valid_roles = {"composer", "lyricist", "composer_lyricist"}
                if role not in valid_roles:
                    errors.append(ValidationError(
                        field=f"{field_prefix}.role",
                        code="INVALID_ROLE",
                        message=f"Invalid writer role. Must be one of: {valid_roles}"
                    ))
                roles_seen.add(role)
            
            # Contribution percentage validation
            if "contribution_percentage" in writer and writer["contribution_percentage"] is not None:
                contribution = writer["contribution_percentage"]
                try:
                    contribution_decimal = Decimal(str(contribution))
                    if contribution_decimal < 0 or contribution_decimal > 100:
                        errors.append(ValidationError(
                            field=f"{field_prefix}.contribution_percentage",
                            code="INVALID_CONTRIBUTION",
                            message="Contribution must be between 0 and 100"
                        ))
                    else:
                        total_contribution += contribution_decimal
                except (ValueError, TypeError):
                    errors.append(ValidationError(
                        field=f"{field_prefix}.contribution_percentage",
                        code="INVALID_CONTRIBUTION_FORMAT",
                        message="Contribution percentage must be a valid number"
                    ))
            
            # Publishing and writer share validation
            for share_field in ["publishing_share", "writer_share"]:
                if share_field in writer and writer[share_field] is not None:
                    try:
                        share = Decimal(str(writer[share_field]))
                        if share < 0 or share > 100:
                            errors.append(ValidationError(
                                field=f"{field_prefix}.{share_field}",
                                code="INVALID_SHARE",
                                message=f"{share_field.replace('_', ' ').title()} must be between 0 and 100"
                            ))
                    except (ValueError, TypeError):
                        errors.append(ValidationError(
                            field=f"{field_prefix}.{share_field}",
                            code="INVALID_SHARE_FORMAT",
                            message=f"{share_field.replace('_', ' ').title()} must be a valid number"
                        ))
        
        # Check total contribution doesn't exceed 100%
        if total_contribution > 100:
            errors.append(ValidationError(
                field="writers",
                code="CONTRIBUTION_EXCEEDS_100",
                message=f"Total contribution percentage cannot exceed 100% (current: {total_contribution}%)"
            ))
        
        # Business rule: Must have either composer or composer_lyricist
        if not ("composer" in roles_seen or "composer_lyricist" in roles_seen):
            errors.append(ValidationError(
                field="writers",
                code="MISSING_COMPOSER",
                message="Work must have at least one composer or composer_lyricist"
            ))
        
        return errors


class SongwriterRegistrationRules:
    """Business rules for songwriter registration."""
    
    @staticmethod
    def validate_songwriter_creation(songwriter_data: dict, tenant_context: TenantContext) -> ValidationResult:
        """Validate songwriter creation request."""
        errors = []
        
        # Required fields
        required_fields = ["first_name", "last_name"]
        for field in required_fields:
            if not songwriter_data.get(field) or len(songwriter_data[field].strip()) == 0:
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        # Name length validation
        if "first_name" in songwriter_data and len(songwriter_data["first_name"]) > 100:
            errors.append(ValidationError(
                field="first_name",
                code="FIRST_NAME_TOO_LONG",
                message="First name cannot exceed 100 characters"
            ))
        
        if "last_name" in songwriter_data and len(songwriter_data["last_name"]) > 100:
            errors.append(ValidationError(
                field="last_name",
                code="LAST_NAME_TOO_LONG",
                message="Last name cannot exceed 100 characters"
            ))
        
        # Email validation
        if "email" in songwriter_data and songwriter_data["email"]:
            email_errors = EmailValidator.validate(songwriter_data["email"])
            errors.extend(email_errors)
        
        # Phone validation
        if "phone" in songwriter_data and songwriter_data["phone"]:
            phone_errors = PhoneValidator.validate(
                songwriter_data["phone"],
                songwriter_data.get("birth_country")
            )
            errors.extend(phone_errors)
        
        # IPI validation (basic format check)
        ipi = songwriter_data.get("ipi")
        if ipi and (len(ipi) < 8 or len(ipi) > 15 or not ipi.replace("-", "").replace(".", "").isdigit()):
            errors.append(ValidationError(
                field="ipi",
                code="INVALID_IPI_FORMAT",
                message="IPI must be 8-15 digits, may contain hyphens or dots"
            ))
        
        # ISNI validation (basic format check)
        isni = songwriter_data.get("isni")
        if isni and (len(isni) != 16 or not isni.replace(" ", "").isdigit()):
            errors.append(ValidationError(
                field="isni",
                code="INVALID_ISNI_FORMAT",
                message="ISNI must be 16 digits"
            ))
        
        # Country code validation
        for field in ["birth_country", "nationality"]:
            if field in songwriter_data and songwriter_data[field]:
                country = songwriter_data[field]
                if len(country) != 2 or not country.isalpha():
                    errors.append(ValidationError(
                        field=field,
                        code="INVALID_COUNTRY_CODE",
                        message=f"{field.replace('_', ' ').title()} must be a 2-letter country code"
                    ))
        
        # Status validation
        status = songwriter_data.get("status", "active")
        valid_statuses = {"active", "inactive", "deceased"}
        if status not in valid_statuses:
            errors.append(ValidationError(
                field="status",
                code="INVALID_STATUS",
                message=f"Status must be one of: {valid_statuses}"
            ))
        
        # Deceased date validation
        if status != "deceased" and songwriter_data.get("deceased_date"):
            errors.append(ValidationError(
                field="deceased_date",
                code="DECEASED_DATE_INVALID",
                message="Deceased date can only be set when status is 'deceased'"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class RecordingRegistrationRules:
    """Business rules for recording registration."""
    
    @staticmethod
    def validate_recording_creation(recording_data: dict, tenant_context: TenantContext) -> ValidationResult:
        """Validate recording creation request."""
        errors = []
        
        # Required fields
        required_fields = ["work_id", "title", "artist_name"]
        for field in required_fields:
            if not recording_data.get(field):
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        # Title validation
        title = recording_data.get("title", "")
        if len(title) > 500:
            errors.append(ValidationError(
                field="title",
                code="TITLE_TOO_LONG",
                message="Recording title cannot exceed 500 characters"
            ))
        
        # Artist name validation
        artist_name = recording_data.get("artist_name", "")
        if len(artist_name) > 255:
            errors.append(ValidationError(
                field="artist_name",
                code="ARTIST_NAME_TOO_LONG",
                message="Artist name cannot exceed 255 characters"
            ))
        
        # ISRC validation
        if "isrc" in recording_data and recording_data["isrc"]:
            isrc_errors = ISRCValidator.validate(recording_data["isrc"])
            errors.extend(isrc_errors)
        
        # Duration validation
        if "duration_ms" in recording_data and recording_data["duration_ms"] is not None:
            duration = recording_data["duration_ms"]
            if duration <= 0:
                errors.append(ValidationError(
                    field="duration_ms",
                    code="INVALID_DURATION",
                    message="Duration must be positive"
                ))
            if duration > 86400000:  # 24 hours in ms
                errors.append(ValidationError(
                    field="duration_ms",
                    code="DURATION_TOO_LONG",
                    message="Duration cannot exceed 24 hours"
                ))
        
        # Track/disc number validation
        for field in ["track_number", "disc_number"]:
            if field in recording_data and recording_data[field] is not None:
                number = recording_data[field]
                if number <= 0 or number > 999:
                    errors.append(ValidationError(
                        field=field,
                        code="INVALID_NUMBER",
                        message=f"{field.replace('_', ' ').title()} must be between 1 and 999"
                    ))
        
        # Recording type validation
        recording_type = recording_data.get("recording_type", "studio")
        valid_types = {"studio", "live", "demo", "remix", "remaster", "alternate", "acoustic"}
        if recording_type not in valid_types:
            errors.append(ValidationError(
                field="recording_type",
                code="INVALID_RECORDING_TYPE",
                message=f"Recording type must be one of: {valid_types}"
            ))
        
        # File format validation
        if "file_format" in recording_data and recording_data["file_format"]:
            file_format = recording_data["file_format"].lower()
            valid_formats = {"mp3", "wav", "flac", "aac", "m4a", "ogg", "wma", "aiff"}
            if file_format not in valid_formats:
                errors.append(ValidationError(
                    field="file_format",
                    code="INVALID_FILE_FORMAT",
                    message=f"File format must be one of: {valid_formats}"
                ))
        
        # Contributors validation
        if "contributors" in recording_data:
            contributor_errors = RecordingContributorValidator.validate_contributors(
                recording_data["contributors"]
            )
            errors.extend(contributor_errors)
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class RecordingContributorValidator:
    """Validates recording contributors."""
    
    @staticmethod
    def validate_contributors(contributors_data: List[dict]) -> List[ValidationError]:
        """Validate contributors array."""
        errors = []
        
        if not contributors_data:
            return errors
        
        contributor_role_combinations = set()
        
        for i, contributor in enumerate(contributors_data):
            field_prefix = f"contributors[{i}]"
            
            # Required fields
            if not contributor.get("contributor_name"):
                errors.append(ValidationError(
                    field=f"{field_prefix}.contributor_name",
                    code="CONTRIBUTOR_NAME_REQUIRED",
                    message="Contributor name is required"
                ))
            
            if not contributor.get("role"):
                errors.append(ValidationError(
                    field=f"{field_prefix}.role",
                    code="ROLE_REQUIRED",
                    message="Contributor role is required"
                ))
            
            # Check for duplicate contributor-role-instrument combinations
            name = contributor.get("contributor_name", "")
            role = contributor.get("role", "")
            instrument = contributor.get("instrument", "")
            combination_key = f"{name}:{role}:{instrument}"
            
            if combination_key in contributor_role_combinations:
                errors.append(ValidationError(
                    field=f"{field_prefix}",
                    code="DUPLICATE_CONTRIBUTOR",
                    message="Duplicate contributor-role-instrument combination"
                ))
            contributor_role_combinations.add(combination_key)
            
            # Name length validation
            if len(name) > 255:
                errors.append(ValidationError(
                    field=f"{field_prefix}.contributor_name",
                    code="CONTRIBUTOR_NAME_TOO_LONG",
                    message="Contributor name cannot exceed 255 characters"
                ))
            
            # Role length validation
            if len(role) > 100:
                errors.append(ValidationError(
                    field=f"{field_prefix}.role",
                    code="ROLE_TOO_LONG",
                    message="Role cannot exceed 100 characters"
                ))
        
        return errors


class DuplicateDetectionRules:
    """Rules for detecting potential duplicates."""
    
    @staticmethod
    def check_work_duplicates(work_data: dict, existing_works: List[dict]) -> List[dict]:
        """Check for potential duplicate works."""
        duplicates = []
        title = work_data.get("title", "")
        
        for existing_work in existing_works:
            existing_title = existing_work.get("title", "")
            
            # Check title similarity
            if DuplicateDetector.is_potential_duplicate(title, existing_title):
                duplicates.append({
                    "work_id": existing_work.get("id"),
                    "title": existing_title,
                    "similarity_score": DuplicateDetector.similarity_score(title, existing_title),
                    "match_type": "title"
                })
            
            # Check ISWC match
            if (work_data.get("iswc") and existing_work.get("iswc") and 
                work_data["iswc"] == existing_work["iswc"]):
                duplicates.append({
                    "work_id": existing_work.get("id"),
                    "title": existing_title,
                    "similarity_score": 1.0,
                    "match_type": "iswc"
                })
        
        return duplicates
    
    @staticmethod
    def check_songwriter_duplicates(songwriter_data: dict, existing_songwriters: List[dict]) -> List[dict]:
        """Check for potential duplicate songwriters."""
        duplicates = []
        
        first_name = songwriter_data.get("first_name", "")
        last_name = songwriter_data.get("last_name", "")
        full_name = f"{first_name} {last_name}"
        
        for existing_songwriter in existing_songwriters:
            existing_first = existing_songwriter.get("first_name", "")
            existing_last = existing_songwriter.get("last_name", "")
            existing_full = f"{existing_first} {existing_last}"
            
            # Check name similarity
            if DuplicateDetector.is_potential_duplicate(full_name, existing_full):
                duplicates.append({
                    "songwriter_id": existing_songwriter.get("id"),
                    "name": existing_full,
                    "similarity_score": DuplicateDetector.similarity_score(full_name, existing_full),
                    "match_type": "name"
                })
            
            # Check IPI match
            if (songwriter_data.get("ipi") and existing_songwriter.get("ipi") and 
                songwriter_data["ipi"] == existing_songwriter["ipi"]):
                duplicates.append({
                    "songwriter_id": existing_songwriter.get("id"),
                    "name": existing_full,
                    "similarity_score": 1.0,
                    "match_type": "ipi"
                })
            
            # Check email match
            if (songwriter_data.get("email") and existing_songwriter.get("email") and 
                songwriter_data["email"].lower() == existing_songwriter["email"].lower()):
                duplicates.append({
                    "songwriter_id": existing_songwriter.get("id"),
                    "name": existing_full,
                    "similarity_score": 1.0,
                    "match_type": "email"
                })
        
        return duplicates