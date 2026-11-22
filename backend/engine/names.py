"""Name and domain normalisation, shared by the duplicate and look-alike checks."""
import re

from rapidfuzz import fuzz

# Legal suffixes: dropped before comparing company names ("ABC Logistics Pvt Ltd" == "ABC Logistics").
LEGAL_WORDS = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "corp", "the", "and"}

# Generic words dropped when looking for a brand inside a domain ("bluedart-logistics-india" -> "bluedart").
FILLER_WORDS = ["india", "global", "logistics", "transport", "solutions", "group", "pvt", "ltd",
                "private", "limited", "services", "express", "cargo", "movers", "online", "official"]

# Multi-part endings first, so "abc.co.in" loses ".co.in" and not just ".in".
TLD_SUFFIXES = [".co.in", ".net.in", ".org.in", ".co.uk", ".com.au",
                ".com", ".in", ".net", ".org", ".co", ".io", ".biz", ".info", ".ai", ".app", ".xyz"]


def normalize_domain(url_or_domain: str | None) -> str | None:
    """'https://www.ABC-Logistics.co.in/about' -> 'abc-logistics.co.in'"""
    if not url_or_domain:
        return None
    d = url_or_domain.strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)        # scheme
    d = d.split("/")[0].split("?")[0].split(":")[0]
    d = d.removeprefix("www.")
    return d or None


def domain_label(domain: str | None) -> str | None:
    """'abc-logistics.co.in' -> 'abc-logistics' (the part a person reads as the brand)."""
    d = normalize_domain(domain)
    if not d:
        return None
    for suffix in TLD_SUFFIXES:
        if d.endswith(suffix) and len(d) > len(suffix):
            return d[: -len(suffix)]
    return d.rsplit(".", 1)[0]


def brand_key(text: str | None) -> str:
    """Reduce a domain label or company name to its brand for look-alike comparison:
    lowercase, swap common look-alike characters (0->o, 1->l, rn->m), drop separators and filler words."""
    if not text:
        return ""
    t = text.lower()
    t = t.replace("0", "o").replace("1", "l").replace("rn", "m")
    t = re.sub(r"[^a-z]", "", t)            # hyphens, dots, spaces, other digits
    for word in FILLER_WORDS:
        if t != word:                       # never reduce a name to nothing
            t = t.replace(word, "")
    return t


def normalize_name(name: str | None) -> str:
    """'A.B.C. Logistics Pvt. Ltd.' -> 'abc logistics'"""
    if not name:
        return ""
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace(".", "")).split()
    return " ".join(w for w in words if w not in LEGAL_WORDS)


def name_score(a: str | None, b: str | None) -> float:
    """0-100 similarity of two company names, ignoring word order and legal suffixes."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    return fuzz.token_sort_ratio(na, nb)


def same_person(a: str | None, b: str | None) -> bool:
    """Director names match (order-insensitive, tolerant of a typo)."""
    if not a or not b:
        return False
    return fuzz.token_sort_ratio(normalize_name(a), normalize_name(b)) >= 90
