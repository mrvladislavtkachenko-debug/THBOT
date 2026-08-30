"""URL analysis for extracted links in posts.

Rule-based, works at URL/domain level only (per the spec). It never
navigates to suspicious links. It extracts URLs, normalizes domains,
counts mentions, classifies link type and flags suspicious signs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

URL_RE = re.compile(
    r"(?:(?:https?|ftp)://|www\.)[^\s<>\"']+|t\.me/[^\s<>\"']+",
    re.IGNORECASE,
)

# Domains commonly used for link shorteners / tracking
SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "is.gd", "t.co", "buff.ly",
    "ow.ly", "rebrand.ly", "shorturl.at", "cutt.ly", "rb.gy", "clck.ru",
    "qrco.de", "t.ly", "short.gy", "tiny.cc",
}

SUSPICIOUS_KEYWORDS = {
    "wallet", "payment", "pay", "transfer", "send-money", "withdraw",
    "bonus", "investment", "rewards", "claim", "deposit", "reinvest",
}

# Unusual TLDs often used for throwaway/phishing domains
RISKY_TLDS = {"xyz", "top", "club", "online", "site", "icu", "buzz", "win"}


@dataclass
class LinkInfo:
    raw: str
    domain: str | None = None
    is_shortener: bool = False
    is_risky_tld: bool = False
    has_suspicious_keyword: bool = False
    is_payment: bool = False


@dataclass
class UrlAnalysis:
    total: int = 0
    unique_domains: list[str] = field(default_factory=list)
    domain_counts: dict[str, int] = field(default_factory=dict)
    shortener_count: int = 0
    risky_tld_count: int = 0
    suspicious_keyword_count: int = 0
    payment_link_count: int = 0
    links: list[LinkInfo] = field(default_factory=list)

    @property
    def suspicious_count(self) -> int:
        return (
            self.shortener_count
            + self.risky_tld_count
            + self.suspicious_keyword_count
            + self.payment_link_count
        )


def extract_links(text: str | None) -> list[str]:
    """Extract all URLs from text."""
    if not text:
        return []
    return [m.group(0) for m in URL_RE.finditer(text)]


def _domain_of(raw: str) -> str | None:
    if "://" in raw:
        parsed = urlparse(raw)
        return (parsed.hostname or "").lower() or None
    # handle "www.domain.com/path"
    body = raw.split("/", 2)[2] if raw.lower().startswith("www.") else raw
    if body.startswith("www."):
        body = body[4:]
    return body.split("/")[0].split("?")[0].lower() or None


def analyze_text(text: str | None) -> UrlAnalysis:
    """Analyze all links found in a piece of text."""
    analysis = UrlAnalysis()
    raw_links = extract_links(text)
    analysis.total = len(raw_links)

    for raw in raw_links:
        info = LinkInfo(raw=raw)
        domain = _domain_of(raw)
        info.domain = domain
        if domain:
            analysis.domain_counts[domain] = analysis.domain_counts.get(domain, 0) + 1
            tld = domain.rsplit(".", 1)[-1].lower()
            if domain in SHORTENERS:
                info.is_shortener = True
                analysis.shortener_count += 1
            if tld in RISKY_TLDS:
                info.is_risky_tld = True
                analysis.risky_tld_count += 1
            if any(kw in domain for kw in SUSPICIOUS_KEYWORDS):
                info.has_suspicious_keyword = True
                analysis.suspicious_keyword_count += 1
            if any(kw in domain for kw in {"wallet", "payment", "pay", "transfer", "deposit"}):
                info.is_payment = True
                analysis.payment_link_count += 1
            analysis.links.append(info)

    # unique domains, ordered by frequency
    analysis.unique_domains = sorted(
        analysis.domain_counts, key=lambda d: -analysis.domain_counts[d]
    )
    return analysis


def aggregate_url_analyses(analyses: list[UrlAnalysis]) -> UrlAnalysis:
    """Combine per-post URL analyses into a channel-level summary."""
    combined = UrlAnalysis()
    for a in analyses:
        combined.total += a.total
        combined.shortener_count += a.shortener_count
        combined.risky_tld_count += a.risky_tld_count
        combined.suspicious_keyword_count += a.suspicious_keyword_count
        combined.payment_link_count += a.payment_link_count
        for d, c in a.domain_counts.items():
            combined.domain_counts[d] = combined.domain_counts.get(d, 0) + c
    combined.unique_domains = sorted(
        combined.domain_counts, key=lambda d: -combined.domain_counts[d]
    )
    return combined
