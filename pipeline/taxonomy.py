"""Fixed label sets. The LLM must pick from these enums (enforced by JSON schema)."""
import re

ROLES = [
    "Software Engineering",
    "Data / Analytics / ML",
    "Product Management",
    "Design (UI/UX/Graphic)",
    "Sales / Business Development",
    "Marketing",
    "Operations / Supply Chain",
    "Finance / Accounting",
    "HR / Recruiting",
    "Customer Support / Success",
    "Content / Writing",
    "Consulting / Strategy",
    "Core Engineering (Mech/Civil/Electrical)",
    "Other",
]

CITIES = [
    "Bengaluru",
    "Mumbai",
    "Delhi NCR",
    "Hyderabad",
    "Pune",
    "Chennai",
    "Kolkata",
    "Ahmedabad",
    "Remote",
    "Other India",
    "India (unspecified)",
]

LEVELS = ["Internship", "Fresher", "Early career", "Experienced"]

# Deterministic alias map. Runs before/after the LLM; when the raw location string
# unambiguously maps to exactly one canonical city, it wins over the LLM.
CITY_ALIASES = {
    "Bengaluru": ["bengaluru", "bangalore", "bengalore", "blr"],
    "Mumbai": ["mumbai", "bombay", "navi mumbai", "thane", "powai"],
    "Delhi NCR": ["delhi", "new delhi", "gurugram", "gurgaon", "noida", "ghaziabad", "faridabad", "ncr"],
    "Hyderabad": ["hyderabad", "secunderabad"],
    "Pune": ["pune"],
    "Chennai": ["chennai", "madras"],
    "Kolkata": ["kolkata", "calcutta"],
    "Ahmedabad": ["ahmedabad", "gandhinagar"],
}
REMOTE_WORDS = ["remote", "work from home", "wfh", "anywhere in india"]


def cities_in(location: str) -> list[str]:
    """Return canonical cities mentioned in a raw location string, in order."""
    loc = (location or "").lower()
    found = []
    for canon, aliases in CITY_ALIASES.items():
        for a in aliases:
            if re.search(rf"\b{re.escape(a)}\b", loc):
                found.append(canon)
                break
    return found


def cities_from_alias(location: str) -> list[str] | None:
    """Deterministic canonical cities if the raw string names known cities / remote, else None
    (None -> the LLM decides, e.g. 'Raipur, CG' -> Other India, 'IND' -> India (unspecified))."""
    found = cities_in(location)
    loc = (location or "").lower()
    if any(w in loc for w in REMOTE_WORDS):
        found.append("Remote")
    return found or None
