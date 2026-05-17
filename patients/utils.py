import re


def normalize_phone(value):
    """Strip all non-digit characters from a phone number."""
    return re.sub(r"\D+", "", value or "")


def format_phone_display(phone):
    """Format a phone number for display.

    Supports:
      - North American 10-digit: +1 (555) 123-4567
      - 11-digit starting with 1: +1 (555) 123-4567
      - Philippine mobile 10-digit starting with 9: +63 912 345 6789
      - Generic fallback for other lengths
    """
    digits = normalize_phone(phone)
    if not digits:
        return phone or ""

    # North American / +1 variants
    if len(digits) == 10:
        return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    # Philippine mobile (11 digits starting with 09)
    if len(digits) == 11 and digits.startswith("09"):
        return f"+63 {digits[1:4]} {digits[4:7]} {digits[7:]}"
    if len(digits) == 12 and digits.startswith("63") and digits[2] == "9":
        return f"+63 {digits[2:5]} {digits[5:8]} {digits[8:]}"

    # Generic: group in threes from the right
    if len(digits) > 10:
        country = digits[:-10]
        rest = digits[-10:]
        return f"+{country} {rest[:3]} {rest[3:6]} {rest[6:]}"

    return digits
