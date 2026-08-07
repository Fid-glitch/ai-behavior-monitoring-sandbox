"""
Prompt Preprocessing Module

Handles the cleaning, validation, and normalization of user prompts
before they are forwarded to the Prompt Injection Detection module.

Functions:
    - clean_prompt(prompt): Removes excess whitespace and control characters.
    - validate_prompt(prompt): Checks emptiness and length constraints.
    - preprocess_prompt(prompt): Orchestrates cleaning and validation.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

# Maximum allowed prompt length (in characters)
MAX_PROMPT_LENGTH = 5000

# Set up a module-level logger
logger = logging.getLogger(__name__)


def clean_prompt(prompt: str) -> str:
    """
    Clean the input prompt by removing unnecessary whitespace and control characters.

    Steps performed:
        1. Strip leading and trailing whitespace.
        2. Replace any sequence of whitespace characters (including newlines,
           tabs, etc.) with a single space.
        3. Remove ASCII control characters (except common whitespace like
           space, tab, newline, carriage return).

    Args:
        prompt: The raw user input string.

    Returns:
        A cleaned version of the prompt string.
    """
    if not isinstance(prompt, str):
        raise TypeError(f"Expected a string, got {type(prompt).__name__}")

    # Step 1: Strip leading/trailing whitespace
    cleaned = prompt.strip()

    # Step 2: Replace multiple whitespace characters (spaces, tabs, newlines)
    # with a single space
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Step 3: Remove unnecessary ASCII control characters (0x00-0x1F, 0x7F)
    # but preserve whitespace characters that are already normalized
    # \t (0x09), \n (0x0A), \r (0x0D) are already handled by \s+ above
    # We explicitly remove remaining control chars
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned)

    logger.debug("Prompt cleaned successfully (length: %d -> %d)", len(prompt), len(cleaned))
    return cleaned


def validate_prompt(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Validate the prompt string against business rules.

    Validation rules:
        - Prompt must not be empty (after cleaning).
        - Prompt must not exceed MAX_PROMPT_LENGTH characters.

    Args:
        prompt: The prompt string to validate (typically already cleaned).

    Returns:
        A tuple of (is_valid, error_message).
        - is_valid: True if the prompt passes all validation checks.
        - error_message: None if valid, otherwise a descriptive error string.
    """
    # Check for empty prompt
    if not prompt or not prompt.strip():
        logger.warning("Validation failed: prompt is empty")
        return False, "Prompt cannot be empty. Please provide a valid input."

    # Check maximum length
    if len(prompt) > MAX_PROMPT_LENGTH:
        logger.warning(
            "Validation failed: prompt exceeds maximum length (%d > %d)",
            len(prompt),
            MAX_PROMPT_LENGTH,
        )
        return (
            False,
            f"Prompt exceeds the maximum allowed length of {MAX_PROMPT_LENGTH} characters. "
            f"Current length: {len(prompt)} characters.",
        )

    logger.debug("Prompt validation passed (length: %d)", len(prompt))
    return True, None


def preprocess_prompt(prompt: str) -> Dict[str, Any]:
    """
    Preprocess a user prompt: clean, validate, and return the result.

    This function orchestrates the full preprocessing pipeline:
        1. Clean the prompt (remove excess whitespace, control chars).
        2. Validate the cleaned prompt (empty check, length check).
        3. Return a structured result containing both original and cleaned
           versions, along with status information.

    Args:
        prompt: The raw user input string.

    Returns:
        A dictionary with the following keys:
            - original_prompt (str): The raw input as received.
            - cleaned_prompt (str): The prompt after cleaning.
            - is_valid (bool): Whether the prompt passed validation.
            - error (Optional[str]): Error message if validation failed, else None.
            - preprocessed (bool): True if the prompt was fully processed.

    Example:
        >>> result = preprocess_prompt("  Hello, World!  ")
        >>> result["is_valid"]
        True
        >>> result["cleaned_prompt"]
        'Hello, World!'
    """
    logger.info("Starting prompt preprocessing")

    # Store the original prompt
    original_prompt = prompt

    try:
        # Step 1: Clean the prompt
        cleaned_prompt = clean_prompt(prompt)

        # Step 2: Validate the cleaned prompt
        is_valid, error_message = validate_prompt(cleaned_prompt)

        if not is_valid:
            logger.warning("Prompt preprocessing failed validation: %s", error_message)
            return {
                "original_prompt": original_prompt,
                "cleaned_prompt": cleaned_prompt,
                "is_valid": False,
                "error": error_message,
                "preprocessed": False,
            }

        # Step 3: Success — return the preprocessed result
        logger.info(
            "Prompt preprocessing completed successfully (original: %d chars, cleaned: %d chars)",
            len(original_prompt),
            len(cleaned_prompt),
        )
        return {
            "original_prompt": original_prompt,
            "cleaned_prompt": cleaned_prompt,
            "is_valid": True,
            "error": None,
            "preprocessed": True,
        }

    except TypeError as e:
        logger.error("TypeError during preprocessing: %s", str(e))
        return {
            "original_prompt": original_prompt,
            "cleaned_prompt": "",
            "is_valid": False,
            "error": f"Input type error: {str(e)}",
            "preprocessed": False,
        }
    except Exception as e:
        logger.exception("Unexpected error during prompt preprocessing: %s", str(e))
        return {
            "original_prompt": original_prompt,
            "cleaned_prompt": "",
            "is_valid": False,
            "error": f"An unexpected error occurred during preprocessing: {str(e)}",
            "preprocessed": False,
        }
