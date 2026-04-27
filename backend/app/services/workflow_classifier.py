"""Workflow classification service.

Classifies user requests into workflow categories using keyword matching
and pattern detection.
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re
import logging

from app.models.models import WorkflowCategory

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of workflow classification."""
    category: WorkflowCategory
    subcategory: Optional[str]
    confidence: int  # 0-100
    keywords: List[str]


# ==============================================================================
# Category Keywords
# ==============================================================================

CATEGORY_PATTERNS = {
    WorkflowCategory.BUG_FIX: {
        "keywords": [
            "bug", "error", "issue", "problem", "broken", "fix", "debug",
            "troubleshoot", "diagnose", "not working", "failing", "crash",
            "exception", "stack trace", "failure",
        ],
        "subcategories": {
            "error_investigation": ["error", "exception", "stack trace"],
            "debugging": ["debug", "troubleshoot", "diagnose"],
            "fix_implementation": ["fix", "resolve", "repair"],
        }
    },
    WorkflowCategory.FEATURE: {
        "keywords": [
            "create", "build", "implement", "add", "new", "develop",
            "make", "construct", "setup", "configure", "generate",
        ],
        "subcategories": {
            "new_feature": ["create", "add", "new", "build"],
            "configuration": ["configure", "setup", "set up"],
            "implementation": ["implement", "develop", "construct"],
        }
    },
    WorkflowCategory.ANALYSIS: {
        "keywords": [
            "analyze", "review", "evaluate", "assess", "examine", "inspect",
            "check", "investigate", "compare", "explain", "understand",
            "how does", "what is", "why",
        ],
        "subcategories": {
            "code_review": ["review", "inspect", "examine"],
            "investigation": ["investigate", "analyze", "assess"],
            "explanation": ["explain", "understand", "how does", "what is"],
        }
    },
    WorkflowCategory.QUESTION: {
        "keywords": [
            "what", "where", "when", "who", "which", "?",
            "tell me", "show me", "can you", "is there",
        ],
        "subcategories": {
            "information": ["what", "where", "which"],
            "capability": ["can you", "is there", "do you"],
            "request": ["tell me", "show me", "give me"],
        }
    },
    WorkflowCategory.WORKFLOW: {
        "keywords": [
            "first", "then", "after", "next", "step",
            "and then", "followed by", "sequence", "process",
        ],
        "subcategories": {
            "multi_step": ["first", "then", "next", "step"],
            "process": ["process", "sequence", "workflow"],
        }
    },
    WorkflowCategory.CREATIVE: {
        "keywords": [
            "design", "brainstorm", "suggest", "idea", "creative",
            "draft", "compose", "write", "generate ideas",
        ],
        "subcategories": {
            "design": ["design", "architecture", "structure"],
            "ideation": ["brainstorm", "suggest", "idea"],
            "composition": ["draft", "compose", "write"],
        }
    },
    WorkflowCategory.ADMIN: {
        "keywords": [
            "config", "settings", "permission", "user", "admin",
            "manage", "setup system", "install", "deploy",
        ],
        "subcategories": {
            "configuration": ["config", "settings", "configure"],
            "user_management": ["user", "permission", "access"],
            "deployment": ["deploy", "install", "setup system"],
        }
    },
}


# ==============================================================================
# Classification Logic
# ==============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for classification."""
    return text.lower().strip()


def extract_keywords(text: str, patterns: Dict) -> List[str]:
    """Extract matched keywords from text."""
    normalized = normalize_text(text)
    matched = []

    for keyword in patterns["keywords"]:
        if keyword in normalized:
            matched.append(keyword)

    return matched


def calculate_confidence(
    matched_keywords: List[str],
    total_patterns: int,
    text_length: int,
) -> int:
    """
    Calculate confidence score (0-100).

    Factors:
    - Number of matched keywords
    - Ratio to total patterns
    - Text length (longer = more context)
    """
    if not matched_keywords:
        return 0

    # Base confidence from keyword matches
    keyword_score = min(len(matched_keywords) * 20, 60)

    # Bonus for multiple matches
    match_ratio = len(matched_keywords) / max(total_patterns, 1)
    ratio_bonus = int(match_ratio * 30)

    # Small bonus for longer text (more context)
    length_bonus = min(text_length // 50, 10)

    total = keyword_score + ratio_bonus + length_bonus
    return min(total, 100)


def detect_subcategory(
    text: str,
    subcategories: Dict[str, List[str]]
) -> Optional[str]:
    """Detect subcategory based on keyword matching."""
    normalized = normalize_text(text)

    for subcategory, keywords in subcategories.items():
        for keyword in keywords:
            if keyword in normalized:
                return subcategory

    return None


def classify_workflow(request_text: str) -> ClassificationResult:
    """
    Classify user request into workflow category.

    Args:
        request_text: User's request text

    Returns:
        ClassificationResult with category, subcategory, confidence, and keywords
    """
    if not request_text or not request_text.strip():
        return ClassificationResult(
            category=WorkflowCategory.UNKNOWN,
            subcategory=None,
            confidence=0,
            keywords=[],
        )

    normalized = normalize_text(request_text)
    text_length = len(request_text)

    # Track best match
    best_category = WorkflowCategory.UNKNOWN
    best_confidence = 0
    best_keywords = []
    best_subcategory = None

    # Check each category
    for category, patterns in CATEGORY_PATTERNS.items():
        keywords = extract_keywords(request_text, patterns)

        if keywords:
            confidence = calculate_confidence(
                keywords,
                len(patterns["keywords"]),
                text_length,
            )

            if confidence > best_confidence:
                best_category = category
                best_confidence = confidence
                best_keywords = keywords
                best_subcategory = detect_subcategory(
                    request_text,
                    patterns.get("subcategories", {})
                )

    # If no strong match, classify as QUESTION or UNKNOWN
    if best_confidence < 30:
        # Check if it's a simple question
        if "?" in request_text or any(
            word in normalized for word in ["what", "how", "why", "where", "when"]
        ):
            best_category = WorkflowCategory.QUESTION
            best_confidence = 50
            best_subcategory = "information"
        else:
            best_category = WorkflowCategory.UNKNOWN
            best_confidence = 20

    result = ClassificationResult(
        category=best_category,
        subcategory=best_subcategory,
        confidence=best_confidence,
        keywords=best_keywords,
    )

    logger.info(
        f"Classified request as {result.category.value}",
        extra={
            "category": result.category.value,
            "subcategory": result.subcategory,
            "confidence": result.confidence,
            "keywords": result.keywords,
        }
    )

    return result


def is_emerging_workflow(
    category: WorkflowCategory,
    confidence: int,
    threshold: int = 40,
) -> bool:
    """
    Determine if workflow is emerging (low confidence or unknown).

    Args:
        category: Classified category
        confidence: Classification confidence
        threshold: Confidence threshold for known workflows

    Returns:
        True if emerging, False if known
    """
    return (
        category == WorkflowCategory.UNKNOWN
        or confidence < threshold
    )
