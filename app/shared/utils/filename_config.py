# -*- coding: utf-8 -*-
"""
backend/app/utils/filename_config.py

Configuration settings for filename sanitization system.
Provides configurable parameters for sanitization behavior.

Autor: Ixchel Beristain
Creado: 26/09/2025
"""

from typing import Dict, Set, Optional
from dataclasses import dataclass


@dataclass
class FilenameSanitizationConfig:
    """Configuration for filename sanitization behavior"""
    
    # Maximum filename length
    max_filename_length: int = 120
    
    # Default filename for invalid/empty cases
    default_filename: str = "archivo"
    
    # Maximum extension length to preserve
    max_extension_length: int = 10
    
    # Character replacement settings
    replacement_char: str = "-"
    space_replacement: str = " "  # Keep spaces by default in permissive mode
    
    # Unicode normalization form (NFC recommended)
    unicode_normalization: str = "NFC"
    
    # Enable/disable specific sanitization steps
    enable_unicode_transliteration: bool = False  # Preserve accents by default in permissive mode
    enable_length_limitation: bool = True
    enable_extension_preservation: bool = True
    enable_strict_mode: bool = False  # Controls how aggressive sanitization is
    
    # Logging settings
    log_sanitization_changes: bool = True
    log_problematic_characters: bool = True


class FilenameSanitizationRules:
    """Centralized rules and character mappings for filename sanitization"""
    
    # Unicode character replacements (comprehensive mapping)
    UNICODE_REPLACEMENTS: Dict[str, str] = {
        # Dashes and hyphens
        '—': '-',  # U+2014 EM DASH
        '–': '-',  # U+2013 EN DASH
        '−': '-',  # U+2212 MINUS SIGN
        '⸺': '-',  # U+2E3A TWO-EM DASH
        '⸻': '-',  # U+2E3B THREE-EM DASH
        
        # Quotes and apostrophes
        ''': "'",  # U+2018 LEFT SINGLE QUOTATION MARK
        ''': "'",  # U+2019 RIGHT SINGLE QUOTATION MARK
        '"': '"',  # U+201C LEFT DOUBLE QUOTATION MARK
        '"': '"',  # U+201D RIGHT DOUBLE QUOTATION MARK
        '‚': "'",  # U+201A SINGLE LOW-9 QUOTATION MARK
        '„': '"',  # U+201E DOUBLE LOW-9 QUOTATION MARK
        '‹': '<',  # U+2039 SINGLE LEFT-POINTING ANGLE QUOTATION MARK
        '›': '>',  # U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
        '«': '"',  # U+00AB LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
        '»': '"',  # U+00BB RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
        
        # Spaces (various Unicode space characters)
        '\u00A0': ' ',  # NON-BREAKING SPACE
        '\u2000': ' ',  # EN QUAD
        '\u2001': ' ',  # EM QUAD
        '\u2002': ' ',  # EN SPACE
        '\u2003': ' ',  # EM SPACE
        '\u2004': ' ',  # THREE-PER-EM SPACE
        '\u2005': ' ',  # FOUR-PER-EM SPACE
        '\u2006': ' ',  # SIX-PER-EM SPACE
        '\u2007': ' ',  # FIGURE SPACE
        '\u2008': ' ',  # PUNCTUATION SPACE
        '\u2009': ' ',  # THIN SPACE
        '\u200A': ' ',  # HAIR SPACE
        
        # Dots and symbols
        '…': '...',  # U+2026 HORIZONTAL ELLIPSIS
        '•': '-',    # U+2022 BULLET
        '·': '-',    # U+00B7 MIDDLE DOT
        '‧': '-',    # U+2027 HYPHENATION POINT
        '⋅': '-',    # U+22C5 DOT OPERATOR
        
        # Special symbols
        '&': 'and',  # Ampersand (can be problematic in URLs)
        '©': 'c',    # U+00A9 COPYRIGHT SIGN
        '®': 'r',    # U+00AE REGISTERED SIGN
        '™': 'tm',   # U+2122 TRADE MARK SIGN
        '§': 's',    # U+00A7 SECTION SIGN
        '¶': 'p',    # U+00B6 PILCROW SIGN
        '†': '+',    # U+2020 DAGGER
        '‡': '++',   # U+2021 DOUBLE DAGGER
    }
    
    # Characters that are problematic for file systems and storage
    FILESYSTEM_PROBLEMATIC: Set[str] = {
        '/', '\\', ':', '*', '?', '"', '<', '>', '|', '#', '%', '+', ';', ',', '=',
        '[', ']', '{', '}', '^', '`', '~'
    }
    
    # Control characters (ASCII 0-31 and 127-159)
    CONTROL_CHARS_PATTERN = r'[\x00-\x1f\x7f-\x9f]'
    
    # Supabase Storage specific problematic characters
    SUPABASE_PROBLEMATIC: Set[str] = {
        '—', '–', ''', ''', '"', '"', '…', '•', '·', '/', '\\', ':', '*', '?', 
        '"', '<', '>', '|', '#', '%', '+', ';', ',', '=', '[', ']', '{', '}', 
        '^', '`', '~'
    }
    
    # Safe character pattern (only allow word chars, dots, dashes)
    SAFE_CHARS_PATTERN = r'^[\w\.-]+$'
    
    @classmethod
    def get_problematic_chars_in_filename(cls, filename: str) -> Dict[str, list]:
        """
        Analyze a filename and return categorized problematic characters.
        
        Args:
            filename: Filename to analyze
            
        Returns:
            Dict with categories of problematic characters found
        """
        analysis = {
            'unicode_replaceable': [],
            'filesystem_problematic': [],
            'supabase_problematic': [],
            'control_chars': []
        }
        
        for char in filename:
            if char in cls.UNICODE_REPLACEMENTS:
                analysis['unicode_replaceable'].append(char)
            if char in cls.FILESYSTEM_PROBLEMATIC:
                analysis['filesystem_problematic'].append(char)
            if char in cls.SUPABASE_PROBLEMATIC:
                analysis['supabase_problematic'].append(char)
            if ord(char) < 32 or (127 <= ord(char) <= 159):
                analysis['control_chars'].append(char)
        
        return analysis


# Default configuration instance (permissive for legacy compatibility)
DEFAULT_CONFIG = FilenameSanitizationConfig()

# Strict configuration for production/Supabase
STRICT_CONFIG = FilenameSanitizationConfig(
    space_replacement="-",
    enable_unicode_transliteration=True,
    enable_strict_mode=True
)

# Export configuration functions
def get_sanitization_config(strict_mode: bool = False) -> FilenameSanitizationConfig:
    """Get the current sanitization configuration"""
    return STRICT_CONFIG if strict_mode else DEFAULT_CONFIG

def update_sanitization_config(**kwargs) -> None:
    """Update sanitization configuration parameters"""
    global DEFAULT_CONFIG
    for key, value in kwargs.items():
        if hasattr(DEFAULT_CONFIG, key):
            setattr(DEFAULT_CONFIG, key, value)
        else:
            raise ValueError(f"Invalid configuration parameter: {key}")

def get_production_config() -> FilenameSanitizationConfig:
    """Get production-ready configuration for Supabase Storage"""
    return STRICT_CONFIG

# Export rules and mappings
__all__ = [
    'FilenameSanitizationConfig',
    'FilenameSanitizationRules', 
    'DEFAULT_CONFIG',
    'get_sanitization_config',
    'update_sanitization_config'
]






