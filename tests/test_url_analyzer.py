"""Tests for the rule-based URL analyzer."""

from app.services.url_analyzer import analyze_text, extract_links, aggregate_url_analyses


def test_extract_links():
    text = "Visit https://t.me/channel and http://example.com/path ok"
    links = extract_links(text)
    assert len(links) >= 2
    assert any("t.me" in l for l in links)


def test_domain_counts():
    a = analyze_text("go to https://example.com/a and https://example.com/b and https://other.org")
    assert a.domain_counts["example.com"] == 2
    assert a.domain_counts["other.org"] == 1
    assert a.unique_domains[0] == "example.com"


def test_shortener_detected():
    a = analyze_text("link: https://bit.ly/abc")
    assert a.shortener_count == 1
    assert a.suspicious_count >= 1


def test_risky_tld():
    a = analyze_text("https://bonus.xyz/claim")
    assert a.risky_tld_count == 1


def test_payment_keyword():
    a = analyze_text("send to https://wallet-transfer.pay")
    assert a.payment_link_count >= 1


def test_aggregate():
    a1 = analyze_text("https://example.com")
    a2 = analyze_text("https://bit.ly/x")
    combined = aggregate_url_analyses([a1, a2])
    assert combined.total == 2
    assert combined.shortener_count == 1
