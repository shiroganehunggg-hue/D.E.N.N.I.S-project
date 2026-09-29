"""
Safety-net post-processor for DENNIS's self-reference / title rules.

The system prompt already instructs the model to use "tôi"/"Sếp" only in
Vietnamese responses and "I"/"boss" only in English ones. This module is a
second line of defense: prompt-following is not guaranteed across all 8
fallback providers (some are much weaker at holding a subtle instruction
like this over a long response), so we scan the FINAL text and fix any
leaks before it reaches the user.

Usage:
    from language_guard import enforce_language_consistency

    reply = router.generate(messages)
    reply = enforce_language_consistency(reply)
"""

import re

# Rough Vietnamese-diacritic character set, used only to guess the
# dominant language of a piece of text — not a full language detector.
_VIETNAMESE_CHARS = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)

# Words that legitimately contain "bạn" but are NOT the user's title
# (e.g. "bạn bè" = friends, "bạn học" = classmate). Extend as needed.
_BAN_COMPOUND_EXCEPTIONS = (
    "bè", "học", "gái", "trai", "thân", "đời", "hàng", "diễn",
)


def _looks_vietnamese(text: str) -> bool:
    """Heuristic: does this text contain enough Vietnamese diacritics
    to be considered a Vietnamese response, rather than English?

    "Sếp" and "tôi" are stripped out before counting — otherwise a
    single leaked "Sếp" in an English sentence (which itself contains
    a diacritic) would trick this into misclassifying the response as
    Vietnamese, which is exactly the leak we're trying to catch.
    """
    if not text:
        return False
    stripped = re.sub(r"\b(Sếp|tôi)\b", "", text, flags=re.IGNORECASE)
    hits = len(_VIETNAMESE_CHARS.findall(stripped))
    # Threshold is deliberately low: even a couple of accented words
    # elsewhere in the text is a strong signal the sentence is Vietnamese.
    return hits >= 2


def _fix_vietnamese_response(text: str) -> str:
    """In a Vietnamese response, replace any stray 'bạn' used as the
    user's title with 'Sếp', but leave compound words like
    'bạn bè' / 'bạn học' alone."""

    def _replace(match: re.Match) -> str:
        start, end = match.span()
        following = text[end:end + 12].lstrip()
        for exception in _BAN_COMPOUND_EXCEPTIONS:
            if following.startswith(exception):
                return match.group(0)  # leave untouched, it's a compound word
        # Preserve capitalization of the original word
        original = match.group(0)
        return "Sếp" if original[0].islower() else "Sếp"

    return re.sub(r"\bbạn\b", _replace, text, flags=re.IGNORECASE)


def _fix_english_response(text: str) -> str:
    """In an English response, replace any stray Vietnamese
    self-reference/title words that leaked in."""
    text = re.sub(r"\btôi\b", "I", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSếp\b", "boss", text, flags=re.IGNORECASE)
    return text


def enforce_language_consistency(text: str) -> str:
    """Main entry point: detects the response's language and repairs
    any self-reference/title leaks accordingly.

    This does not replace the system prompt rules — it's a cheap,
    deterministic fallback for the cases where a weaker provider
    doesn't follow them perfectly.
    """
    if not text:
        return text

    if _looks_vietnamese(text):
        return _fix_vietnamese_response(text)
    else:
        return _fix_english_response(text)