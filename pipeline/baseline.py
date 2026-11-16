"""Keyword baseline tagger. Used (a) to quantify how much the LLM adds in the eval
and (b) as a fallback so the site still refreshes when the LLM API is unavailable."""
import re

from .taxonomy import cities_from_alias

# Order matters: first match wins. Title is checked before description.
ROLE_RULES = [
    ("Data / Analytics / ML", r"\b(data|analytics?|analyst|machine learning|ml|ai|deep learning|nlp|scientist|bi|business intelligence|mis)\b"),
    ("Software Engineering", r"\b(software|sde|developer|engineer(ing)? - ?(backend|frontend|full ?stack)|backend|frontend|front-end|back-end|full ?stack|devops|sre|android|ios|mobile|web|qa|test(ing)?|automation|java|python|react|node|cloud|security|cyber|platform engineer|programmer|swe)\b"),
    ("Product Management", r"\b(product manager|product management|apm|product intern|product analyst|product owner)\b"),
    ("Design (UI/UX/Graphic)", r"\b(design(er)?|ui|ux|graphic|visual|motion|illustrat\w*|creative)\b"),
    ("Sales / Business Development", r"\b(sales|business development|bd|bde|account executive|inside sales|pre-?sales|partnerships?)\b"),
    ("Marketing", r"\b(marketing|growth|seo|sem|social media|brand|performance marketing|digital marketing|community)\b"),
    ("Content / Writing", r"\b(content|writer|writing|copywrit\w*|editor|journalis\w*)\b"),
    ("Customer Support / Success", r"\b(customer (support|success|service|experience)|support (executive|associate|engineer)|helpdesk|cx)\b"),
    ("HR / Recruiting", r"\b(hr|human resources?|recruit\w*|talent acquisition|people (ops|partner))\b"),
    ("Finance / Accounting", r"\b(finance|financial|accountant|accounting|audit|tax|treasury|ca|fp&a|credit|risk)\b"),
    ("Operations / Supply Chain", r"\b(operations?|ops|supply chain|logistics|procurement|warehouse|fulfil+ment)\b"),
    ("Consulting / Strategy", r"\b(consult\w*|strategy|strategic|chief of staff|founder'?s office)\b"),
    ("Core Engineering (Mech/Civil/Electrical)", r"\b(mechanical|civil|electrical|electronics|production|manufacturing|chemical|hardware|vlsi|embedded)\b"),
]


def baseline_role(title: str, description: str = "") -> str:
    for text in (title or "", (description or "")[:300]):
        t = text.lower()
        for role, pat in ROLE_RULES:
            if re.search(pat, t):
                return role
    return "Other"


def baseline_cities(location: str) -> list[str]:
    return cities_from_alias(location) or ["India (unspecified)"]


def baseline_tag(post: dict) -> dict:
    return {
        "role": baseline_role(post["title"], post.get("description", "")),
        "cities": baseline_cities(post.get("location", "")),
    }
