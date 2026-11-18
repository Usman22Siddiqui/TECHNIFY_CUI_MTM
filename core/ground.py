"""Reject extracted values not present in the source text.

Without it: a hallucinated number silently corrupts the plan.

For every numeric fact, the normalised number must appear in the
normalised source message. Handles Pakistani number formats:
lakh grouping, k suffix, lakh/lac/crore, Roman Urdu and Urdu script
number words, Urdu-Indic digits, and hour-to-minute conversions.
"""

from __future__ import annotations

import re
from typing import Any


# Urdu-Indic & Arabic-Indic digits -> ASCII digits
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# Roman Urdu & Urdu script number words -> integer
_NUMBER_WORDS: dict[str, int] = {
    "ek": 1, "aik": 1, "ایک": 1, "one": 1,
    "do": 2, "dou": 2, "دو": 2, "two": 2,
    "teen": 3, "tiin": 3, "تین": 3, "three": 3,
    "chaar": 4, "char": 4, "چار": 4, "four": 4,
    "paanch": 5, "panch": 5, "paach": 5, "پانچ": 5, "five": 5,
    "chhay": 6, "chhe": 6, "chay": 6, "چھ": 6, "six": 6,
    "saat": 7, "sat": 7, "سات": 7, "seven": 7,
    "aath": 8, "aat": 8, "آٹھ": 8, "eight": 8,
    "nau": 9, "نو": 9, "nine": 9,
    "das": 10, "dus": 10, "دس": 10, "ten": 10,
    "gyarah": 11, "baarah": 12, "barah": 12,
    "terah": 13, "chaudah": 14, "pandrah": 15, "پندرہ": 15,
    "solah": 16, "satrah": 17, "athaarah": 18,
    "unees": 19, "bees": 20, "bis": 20, "بیس": 20,
    "pachees": 25, "pachis": 25,
    "tees": 30, "tiis": 30, "تیس": 30,
    "chaalees": 40, "chalees": 40,
    "pachaas": 50, "pachas": 50, "پچاس": 50,
    "saath": 60,
    "sattar": 70,
    "assi": 80,
    "nabbe": 90,
    "sau": 100, "so": 100, "سو": 100,
}

# Multiplier words (Roman Urdu + Urdu script + English)
_MULTIPLIER_WORDS: dict[str, int] = {
    "hazar": 1_000, "hazaar": 1_000, "hajaar": 1_000, "ہزار": 1_000, "thousand": 1_000,
    "lakh": 100_000, "lac": 100_000, "laakh": 100_000, "لاکھ": 100_000,
    "crore": 10_000_000, "karor": 10_000_000, "karod": 10_000_000, "کروڑ": 10_000_000,
}

_FRACTION_WORDS: dict[str, float] = {
    "saarhay": 0.5, "saadhe": 0.5, "sadhe": 0.5, "ساڑھے": 0.5,
    "dedh": 1.5, "ڈیڑھ": 1.5,
    "dhai": 2.5, "ڈھائی": 2.5,
}

_HOUR_MARKERS = ("hour", "hr", "ghant", "گھنٹ")
_ZERO_MARKERS = ("free", "muft", "zero", "مفت", "صفر")


def _to_ascii_digits(text: str) -> str:
    return text.translate(_DIGIT_TRANSLATION)


def normalise_number(text: str) -> int | None:
    """Try to parse a string as a number using Pakistani conventions.

    Returns:
        Integer value or None if not parseable.
    """
    if not text:
        return None

    s = _to_ascii_digits(text).strip().lower()

    # Remove currency markers
    s = re.sub(r"^(rs\.?|pkr|rupay|rupees?|روپے)\s*", "", s)
    s = re.sub(r"\s*(rs\.?|pkr|rupay|rupees?|روپے)$", "", s)
    s = re.sub(r"/-$", "", s)

    s = s.strip()
    if not s:
        return None

    # Plain number with commas (handles both international and lakh grouping)
    plain = s.replace(",", "")
    try:
        return int(float(plain))
    except ValueError:
        pass

    # K suffix
    k_match = re.match(r"^([\d.]+)\s*k$", s)
    if k_match:
        try:
            return int(round(float(k_match.group(1)) * 1_000))
        except ValueError:
            pass

    # Lakh/lac/hazar/crore suffix
    for word, mult in _MULTIPLIER_WORDS.items():
        pattern = rf"^([\d.]+)\s*{re.escape(word)}$"
        match = re.match(pattern, s)
        if match:
            try:
                return int(round(float(match.group(1)) * mult))
            except ValueError:
                pass

    # Number words
    return _parse_number_words(s)


def _parse_number_words(text: str) -> int | None:
    """Parse Roman Urdu / Urdu script number words."""
    words = _to_ascii_digits(text).strip().lower().split()
    if not words:
        return None

    # Special fractional idioms like "dedh lakh", "dhai hazar", "saarhay che lakh"
    if len(words) == 2 and words[0] in ("dedh", "ڈیڑھ", "dhai", "ڈھائی") and words[1] in _MULTIPLIER_WORDS:
        return int(round(_FRACTION_WORDS[words[0]] * _MULTIPLIER_WORDS[words[1]]))
    if len(words) == 3 and words[0] in ("saarhay", "saadhe", "sadhe", "ساڑھے"):
        base = _NUMBER_WORDS.get(words[1])
        mult = _MULTIPLIER_WORDS.get(words[2])
        if base is not None and mult is not None:
            return int(round((base + 0.5) * mult))

    total = 0
    current = 0

    for word in words:
        if word in _NUMBER_WORDS:
            current += _NUMBER_WORDS[word]
        elif word in _MULTIPLIER_WORDS:
            if current == 0:
                current = 1
            current *= _MULTIPLIER_WORDS[word]
            total += current
            current = 0
        else:
            return None

    total += current
    return total if total > 0 else None


def _extract_all_numbers(text: str) -> set[int]:
    """Extract all numbers (and floats scaled by 60 for hour spans) from text."""
    ascii_text = _to_ascii_digits(text)
    numbers: set[int] = set()

    # 1. Plain integers and comma-separated numbers
    for match in re.finditer(r"[\d,]+(?:\.\d+)?", ascii_text):
        val = normalise_number(match.group())
        if val is not None:
            numbers.add(val)

    # 2. Numbers with K/lakh/hazar/crore suffix
    mult_pattern = "|".join(re.escape(w) for w in list(_MULTIPLIER_WORDS.keys()) + ["k"])
    for match in re.finditer(
        rf"[\d.]+\s*(?:{mult_pattern})\b",
        ascii_text,
        re.IGNORECASE,
    ):
        val = normalise_number(match.group())
        if val is not None:
            numbers.add(val)

    # 3. Number words with multipliers (2-word and 3-word phrases)
    tokens = re.findall(r"[\w\u0600-\u06FF]+", ascii_text.lower())
    for i in range(len(tokens)):
        if tokens[i] in _NUMBER_WORDS:
            numbers.add(_NUMBER_WORDS[tokens[i]])
        if i + 1 < len(tokens) and tokens[i + 1] in _MULTIPLIER_WORDS:
            val = _parse_number_words(f"{tokens[i]} {tokens[i + 1]}")
            if val is not None:
                numbers.add(val)
        if i + 2 < len(tokens) and tokens[i + 2] in _MULTIPLIER_WORDS:
            val = _parse_number_words(f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}")
            if val is not None:
                numbers.add(val)

    # 4. If text mentions hours, allow hour -> minute equivalents (e.g. 4 hours -> 240 min)
    lower_text = ascii_text.lower()
    if any(m in lower_text for m in _ZERO_MARKERS):
        numbers.add(0)
    if any(m in lower_text for m in _HOUR_MARKERS):
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:-|\s)?(?:hours?|hrs?|ghant\w*|گھنٹ\w*)", lower_text):
            try:
                numbers.add(int(round(float(match.group(1)) * 60)))
            except ValueError:
                pass
        for i in range(len(tokens) - 1):
            if tokens[i] in _NUMBER_WORDS and any(tokens[i + 1].startswith(m) for m in _HOUR_MARKERS):
                numbers.add(_NUMBER_WORDS[tokens[i]] * 60)

    return numbers


def ground_facts(
    extracted_messages: list[dict[str, Any]],
    source_messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Verify each numeric fact against its source message.

    For every numeric fact, the normalised number must appear in the
    normalised source message text.

    Args:
        extracted_messages: List of extraction results (dicts with 'i', 'f', etc.)
        source_messages: List of parsed source messages (with 'id', 'text', etc.)

    Returns:
        Tuple of (grounded_messages, dropped_facts).
        dropped_facts: list of {message_id, key, value, reason}.
    """
    source_by_id: dict[int, dict] = {m["id"]: m for m in source_messages}

    grounded = []
    dropped: list[dict[str, Any]] = []

    for ext_msg in extracted_messages:
        msg_id = ext_msg.get("i", 0)
        source = source_by_id.get(msg_id)

        if source is None:
            grounded.append(ext_msg)
            continue

        source_text = source.get("text", "") + " " + source.get("raw", "")
        source_numbers = _extract_all_numbers(source_text)

        kept_facts = []
        for fact in ext_msg.get("f", []):
            value = fact.get("v")

            # Booleans and non-numerics are not number-checked
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                kept_facts.append(fact)
                continue

            int_value = int(round(value))

            if int_value in source_numbers:
                kept_facts.append(fact)
            else:
                dropped.append({
                    "message_id": msg_id,
                    "key": fact.get("key", ""),
                    "value": int_value,
                    "reason": "UNGROUNDED",
                })

        result = dict(ext_msg)
        result["f"] = kept_facts
        grounded.append(result)

    return grounded, dropped
