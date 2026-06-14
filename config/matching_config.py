"""
Member 3 Configuration Module
Matching weights, ATS formatting rules, resume templates, and environment variable loading.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------------------------

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
REDIS_URL: str = os.getenv("REDIS_URL", "")
MONGODB_URI: str = os.getenv("MONGODB_URI", "")
DOCUMENT_OUTPUT_DIR: str = os.getenv("DOCUMENT_OUTPUT_DIR", "./outputs")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
MAX_RECOMMENDATIONS: int = int(os.getenv("MAX_RECOMMENDATIONS", "10"))

# Model assignment — DO NOT change without Lead approval
AGENT_MODEL: str = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Match Weight Defaults
# ---------------------------------------------------------------------------

@dataclass
class MatchWeightDefaults:
    """Default weights for job matching scoring components.
    
    All weights must sum to 1.0.
    """
    skill_weight: float = 0.40
    experience_weight: float = 0.25
    location_weight: float = 0.15
    education_weight: float = 0.10
    preference_weight: float = 0.10

    def validate(self) -> bool:
        """Verify weights sum to 1.0 (within floating-point tolerance)."""
        total = (
            self.skill_weight
            + self.experience_weight
            + self.location_weight
            + self.education_weight
            + self.preference_weight
        )
        return abs(total - 1.0) < 1e-9


DEFAULT_MATCH_WEIGHTS = MatchWeightDefaults()


# ---------------------------------------------------------------------------
# Skill Match Confidence Tiers
# ---------------------------------------------------------------------------

EXACT_MATCH_CONFIDENCE: float = 1.0
SIMILAR_MATCH_CONFIDENCE: float = 0.8
RELATED_MATCH_CONFIDENCE: float = 0.5


# ---------------------------------------------------------------------------
# ATS Formatting Rules
# ---------------------------------------------------------------------------

@dataclass
class ATSFormattingRules:
    """Rules for ATS-compatible resume formatting."""
    allowed_fonts: List[str] = field(
        default_factory=lambda: ["Arial", "Calibri", "Times New Roman"]
    )
    min_font_size: int = 10
    max_font_size: int = 12
    heading_font_size: int = 14
    forbidden_elements: List[str] = field(
        default_factory=lambda: [
            "images",
            "icons",
            "graphics",
            "multi-column",
            "text_boxes",
            "tables",
            "headers_footers",
        ]
    )
    section_order: List[str] = field(
        default_factory=lambda: [
            "Contact Info",
            "Summary",
            "Experience",
            "Education",
            "Skills",
            "Certifications",
        ]
    )
    bullet_character: str = "•"
    max_page_count: int = 2
    output_format: str = "pdf"  # "pdf" or "docx"


ATS_RULES = ATSFormattingRules()


# ---------------------------------------------------------------------------
# Resume Template Options
# ---------------------------------------------------------------------------

RESUME_TEMPLATES: Dict[str, str] = {
    "ats_standard": "data/resume_templates/ats_standard.docx",
    "ats_modern": "data/resume_templates/ats_modern.docx",
    "ats_minimal": "data/resume_templates/ats_minimal.docx",
}

DEFAULT_RESUME_TEMPLATE: str = "ats_standard"


# ---------------------------------------------------------------------------
# Cover Letter Tone Presets
# ---------------------------------------------------------------------------

@dataclass
class TonePreset:
    """Defines a cover letter tone configuration."""
    name: str
    formality: str          # "formal" | "semi-formal" | "conversational"
    key_phrases: List[str]  # Characteristic phrases for the tone
    industries: List[str]   # Industries this tone is appropriate for


COVER_LETTER_TONES: Dict[str, TonePreset] = {
    "professional": TonePreset(
        name="professional",
        formality="formal",
        key_phrases=["I am writing to express", "I am confident that",
                     "I look forward to the opportunity"],
        industries=["finance", "legal", "consulting", "government"],
    ),
    "tech": TonePreset(
        name="tech",
        formality="semi-formal",
        key_phrases=["I'm excited about", "I've been following",
                     "I'd love to contribute"],
        industries=["technology", "software", "startup", "data science"],
    ),
    "creative": TonePreset(
        name="creative",
        formality="conversational",
        key_phrases=["What excites me most", "I bring a unique perspective",
                     "Let's create something amazing"],
        industries=["design", "marketing", "media", "entertainment"],
    ),
}

DEFAULT_COVER_LETTER_TONE: str = "professional"


# ---------------------------------------------------------------------------
# Error Handling Configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Configuration for retry behavior on transient errors."""
    max_retries: int = 3
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 30.0
    backoff_factor: float = 2.0


RETRY_CONFIG = RetryConfig()


# ---------------------------------------------------------------------------
# Keyword Extraction
# ---------------------------------------------------------------------------

KEYWORD_INCLUSION_THRESHOLD: float = 0.80  # 80% keyword inclusion target
MIN_MATCH_SCORE_THRESHOLD: float = 0.0     # Minimum score to include in results


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SKILL_TAXONOMY_PATH = DATA_DIR / "skill_taxonomy.json"
RESUME_TEMPLATES_DIR = DATA_DIR / "resume_templates"
OUTPUTS_DIR = pathlib.Path(DOCUMENT_OUTPUT_DIR)
RESUME_OUTPUT_DIR = OUTPUTS_DIR / "resumes"
COVER_LETTER_OUTPUT_DIR = OUTPUTS_DIR / "cover_letters"
