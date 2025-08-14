"""Validation utilities for business rules and data formats."""

import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import phonenumbers
from langdetect import detect
from fuzzywuzzy import fuzz


@dataclass
class ValidationError:
    """Validation error details."""
    field: str
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class ValidationResult:
    """Result of validation operation."""
    is_valid: bool
    errors: List[ValidationError]


class ISWCValidator:
    """Validator for International Standard Musical Work Code (ISWC)."""
    
    ISWC_PATTERN = re.compile(r"^T-[0-9]{9}-[0-9]$")
    
    @classmethod
    def is_valid_format(cls, iswc: str) -> bool:
        """Check if ISWC has valid format."""
        if not iswc:
            return False
        return bool(cls.ISWC_PATTERN.match(iswc))
    
    @classmethod
    def validate(cls, iswc: Optional[str]) -> List[ValidationError]:
        """Validate ISWC format and checksum."""
        errors = []
        
        if not iswc:
            return errors
        
        if not cls.is_valid_format(iswc):
            errors.append(ValidationError(
                field="iswc",
                code="INVALID_ISWC_FORMAT",
                message="ISWC must be in format T-XXXXXXXXX-X",
                details={"provided": iswc, "expected_format": "T-XXXXXXXXX-X"}
            ))
            return errors
        
        # Validate checksum
        if not cls._validate_checksum(iswc):
            errors.append(ValidationError(
                field="iswc",
                code="INVALID_ISWC_CHECKSUM",
                message="ISWC checksum is invalid",
                details={"provided": iswc}
            ))
        
        return errors
    
    @classmethod
    def _validate_checksum(cls, iswc: str) -> bool:
        """Validate ISWC checksum digit."""
        try:
            # Extract the 9-digit number and check digit
            number_part = iswc[2:11]  # Remove T- prefix
            check_digit = int(iswc[12])  # Get check digit
            
            # Calculate expected check digit using modulo 10
            total = sum(int(digit) * (10 - i) for i, digit in enumerate(number_part))
            expected_check = total % 10
            
            return check_digit == expected_check
        except (ValueError, IndexError):
            return False
    
    @classmethod
    def generate_check_digit(cls, iswc_base: str) -> str:
        """Generate check digit for ISWC base number."""
        if len(iswc_base) != 9 or not iswc_base.isdigit():
            raise ValueError("ISWC base must be 9 digits")
        
        total = sum(int(digit) * (10 - i) for i, digit in enumerate(iswc_base))
        check_digit = total % 10
        
        return f"T-{iswc_base}-{check_digit}"


class ISRCValidator:
    """Validator for International Standard Recording Code (ISRC)."""
    
    ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
    
    @classmethod
    def is_valid_format(cls, isrc: str) -> bool:
        """Check if ISRC has valid format."""
        if not isrc:
            return False
        return bool(cls.ISRC_PATTERN.match(isrc.upper()))
    
    @classmethod
    def validate(cls, isrc: Optional[str]) -> List[ValidationError]:
        """Validate ISRC format."""
        errors = []
        
        if not isrc:
            return errors
        
        isrc_upper = isrc.upper()
        
        if not cls.is_valid_format(isrc_upper):
            errors.append(ValidationError(
                field="isrc",
                code="INVALID_ISRC_FORMAT",
                message="ISRC must be in format: 2 letters + 3 alphanumeric + 7 digits",
                details={
                    "provided": isrc,
                    "expected_format": "CCNNNYYYYYYY (Country + Registrant + Year + ID)"
                }
            ))
            return errors
        
        # Validate country code
        country_code = isrc_upper[:2]
        if not cls._is_valid_country_code(country_code):
            errors.append(ValidationError(
                field="isrc",
                code="INVALID_ISRC_COUNTRY",
                message=f"Invalid country code in ISRC: {country_code}",
                details={"country_code": country_code}
            ))
        
        return errors
    
    @classmethod
    def _is_valid_country_code(cls, code: str) -> bool:
        """Validate ISRC country code."""
        # Basic validation - should be valid ISO 3166-1 alpha-2 code
        # This is a simplified check; in production, use a complete country code list
        return len(code) == 2 and code.isalpha()
    
    @classmethod
    def parse_components(cls, isrc: str) -> Dict[str, str]:
        """Parse ISRC into its components."""
        if not cls.is_valid_format(isrc):
            raise ValueError("Invalid ISRC format")
        
        isrc_upper = isrc.upper()
        return {
            "country_code": isrc_upper[:2],
            "registrant_code": isrc_upper[2:5],
            "year": isrc_upper[5:7],
            "designation": isrc_upper[7:]
        }


class LanguageValidator:
    """Validator for language codes."""
    
    ISO_639_1_PATTERN = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
    
    # Common language codes for validation
    COMMON_LANGUAGES = {
        "en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko",
        "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi", "cs",
        "hu", "ro", "bg", "hr", "sk", "sl", "et", "lv", "lt", "mt"
    }
    
    @classmethod
    def is_valid_iso639_1(cls, language: str) -> bool:
        """Check if language code is valid ISO 639-1 format."""
        if not language:
            return False
        return bool(cls.ISO_639_1_PATTERN.match(language))
    
    @classmethod
    def validate(cls, language: Optional[str]) -> List[ValidationError]:
        """Validate language code."""
        errors = []
        
        if not language:
            return errors
        
        if not cls.is_valid_iso639_1(language):
            errors.append(ValidationError(
                field="language",
                code="INVALID_LANGUAGE_FORMAT",
                message="Language must be valid ISO 639-1 code (e.g., 'en', 'es-MX')",
                details={"provided": language}
            ))
            return errors
        
        # Extract base language code
        base_lang = language.split("-")[0].lower()
        
        # Warn about uncommon language codes
        if base_lang not in cls.COMMON_LANGUAGES:
            errors.append(ValidationError(
                field="language",
                code="UNCOMMON_LANGUAGE_CODE",
                message=f"Uncommon language code: {base_lang}",
                details={"provided": language, "base_language": base_lang}
            ))
        
        return errors
    
    @classmethod
    def detect_language(cls, text: str) -> Optional[str]:
        """Detect language of text."""
        try:
            if len(text.strip()) < 10:
                return None
            
            detected = detect(text)
            return detected if detected in cls.COMMON_LANGUAGES else None
        except:
            return None


class PhoneValidator:
    """Validator for phone numbers."""
    
    @classmethod
    def validate(cls, phone: Optional[str], country_code: Optional[str] = None) -> List[ValidationError]:
        """Validate phone number format."""
        errors = []
        
        if not phone:
            return errors
        
        try:
            # Parse phone number
            parsed = phonenumbers.parse(phone, country_code)
            
            # Check if valid
            if not phonenumbers.is_valid_number(parsed):
                errors.append(ValidationError(
                    field="phone",
                    code="INVALID_PHONE_NUMBER",
                    message="Invalid phone number format",
                    details={"provided": phone}
                ))
            
        except phonenumbers.NumberParseException as e:
            errors.append(ValidationError(
                field="phone",
                code="PHONE_PARSE_ERROR",
                message=f"Failed to parse phone number: {e}",
                details={"provided": phone, "error": str(e)}
            ))
        
        return errors
    
    @classmethod
    def format_international(cls, phone: str, country_code: Optional[str] = None) -> Optional[str]:
        """Format phone number in international format."""
        try:
            parsed = phonenumbers.parse(phone, country_code)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        except:
            pass
        return None


class EmailValidator:
    """Validator for email addresses."""
    
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    
    @classmethod
    def validate(cls, email: Optional[str]) -> List[ValidationError]:
        """Validate email format."""
        errors = []
        
        if not email:
            return errors
        
        if not cls.EMAIL_PATTERN.match(email):
            errors.append(ValidationError(
                field="email",
                code="INVALID_EMAIL_FORMAT",
                message="Invalid email address format",
                details={"provided": email}
            ))
        
        # Additional checks
        if len(email) > 255:
            errors.append(ValidationError(
                field="email",
                code="EMAIL_TOO_LONG",
                message="Email address too long (max 255 characters)",
                details={"provided_length": len(email)}
            ))
        
        return errors


class DuplicateDetector:
    """Utility for detecting potential duplicates."""
    
    @classmethod
    def similarity_score(cls, text1: str, text2: str) -> float:
        """Calculate similarity score between two texts."""
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        norm1 = cls._normalize_text(text1)
        norm2 = cls._normalize_text(text2)
        
        # Calculate similarity using various methods
        ratio = fuzz.ratio(norm1, norm2)
        partial_ratio = fuzz.partial_ratio(norm1, norm2)
        token_sort_ratio = fuzz.token_sort_ratio(norm1, norm2)
        token_set_ratio = fuzz.token_set_ratio(norm1, norm2)
        
        # Weighted average
        return max(ratio, partial_ratio, token_sort_ratio, token_set_ratio) / 100.0
    
    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """Normalize text for comparison."""
        # Convert to lowercase
        text = text.lower()
        
        # Remove common prefixes/suffixes
        prefixes = ["the ", "a ", "an "]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        
        # Remove punctuation and extra spaces
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
    
    @classmethod
    def is_potential_duplicate(cls, text1: str, text2: str, threshold: float = 0.85) -> bool:
        """Check if two texts are potential duplicates."""
        return cls.similarity_score(text1, text2) >= threshold


class DateValidator:
    """Validator for date formats."""
    
    COMMON_DATE_FORMATS = [
        "%Y-%m-%d",
        "%Y/%m/%d", 
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ"
    ]
    
    @classmethod
    def validate_date_string(cls, date_str: Optional[str]) -> List[ValidationError]:
        """Validate date string format."""
        errors = []
        
        if not date_str:
            return errors
        
        # Try to parse with common formats
        parsed_date = None
        for fmt in cls.COMMON_DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        
        if parsed_date is None:
            errors.append(ValidationError(
                field="date",
                code="INVALID_DATE_FORMAT",
                message="Invalid date format",
                details={
                    "provided": date_str,
                    "supported_formats": cls.COMMON_DATE_FORMATS
                }
            ))
        else:
            # Check for reasonable date ranges
            current_year = datetime.now().year
            if parsed_date.year < 1800 or parsed_date.year > current_year + 10:
                errors.append(ValidationError(
                    field="date",
                    code="UNREASONABLE_DATE",
                    message="Date is outside reasonable range",
                    details={
                        "provided": date_str,
                        "parsed_year": parsed_date.year
                    }
                ))
        
        return errors