"""Parse EOSL.ai hardware lifecycle records without guessing family matches."""

import calendar
import re
from datetime import date


def normalize_identifier(value):
    """Ignore casing and punctuation, retaining the complete identifier."""
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def parse_eosl_date(value):
    """Use the last day for month-precision dates; reject other partial dates."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Lifecycle date must be an ISO date or YYYY-MM string")
    if re.fullmatch(r"\d{4}-\d{2}", value):
        year, month = map(int, value.split("-"))
        return date(year, month, calendar.monthrange(year, month)[1])
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"Unsupported lifecycle date: {value!r}")
    return date.fromisoformat(value)


def matching_groups(family, model, part_number):
    """Match explicit SKUs, preferring a configured part number over the model."""
    identifier = normalize_identifier(part_number or model)
    if not identifier:
        return []
    return [
        group
        for group in family.get("skuGroups", [])
        if any(normalize_identifier(sku.get("partNumber")) == identifier for sku in group.get("skus", []))
    ]


def notice_defaults(groups):
    """Require consistent, published lifecycle dates across all matching groups."""
    fields = {
        "end_of_sale": "endOfSale",
        "end_of_support": "endOfServiceLife",
        "end_of_security_patches": "endOfSecuritySupport",
        "end_of_sw_releases": "endOfSwMaintenance",
    }
    candidates = []
    for group in groups:
        if group.get("eoslComputed"):
            raise ValueError("EOSL date is computed rather than published")
        candidates.append({field: parse_eosl_date(group.get(key)) for field, key in fields.items()})
    if not candidates or any(candidate != candidates[0] for candidate in candidates[1:]):
        raise ValueError("No unambiguous lifecycle dates for this part number")
    if not candidates[0]["end_of_sale"] and not candidates[0]["end_of_support"]:
        raise ValueError("No end-of-sale or end-of-support date published")
    raw_dates = [{key: group.get(key) for key in fields.values()} for group in groups]
    sources = sorted({group["sourceUrl"] for group in groups if group.get("sourceUrl")})
    return {
        **candidates[0],
        "comments": (
            "Imported from EOSL.ai. Month-only dates use the last day of the month.\n"
            f"Original dates: {raw_dates}\nVendor sources: {', '.join(sources) or 'Not provided'}"
        ),
    }
