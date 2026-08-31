from backend.app.services.ingestion.pii import RegexPIIScrubber


def test_pii_scrubber_ssn():
    scrubber = RegexPIIScrubber()
    text = "The employee's SSN is 123-45-6789 and another is 987 65 4321."
    res = scrubber.scrub(text)
    assert "[REDACTED_SSN]" in res.scrubbed_text
    assert "123-45-6789" not in res.scrubbed_text
    assert "987 65 4321" not in res.scrubbed_text
    assert "SSN" in res.redaction_types
    assert res.redactions_count == 2


def test_pii_scrubber_credit_card():
    scrubber = RegexPIIScrubber()
    text = "Payment details: 4111-2222-3333-4444 and 5500 0000 0000 0004."
    res = scrubber.scrub(text)
    assert "[REDACTED_CREDIT_CARD]" in res.scrubbed_text
    assert "4111-2222-3333-4444" not in res.scrubbed_text
    assert "CREDIT_CARD" in res.redaction_types


def test_pii_scrubber_email():
    scrubber = RegexPIIScrubber()
    text = "Contact support@enterprise.com or ceo.executive@company.org for details."
    res = scrubber.scrub(text)
    assert "[REDACTED_EMAIL]" in res.scrubbed_text
    assert "support@enterprise.com" not in res.scrubbed_text
    assert "ceo.executive@company.org" not in res.scrubbed_text
    assert "EMAIL" in res.redaction_types


def test_pii_scrubber_phone():
    scrubber = RegexPIIScrubber()
    text = "Call us at +1 (555) 123-4567 or 555-987-6543."
    res = scrubber.scrub(text)
    assert "[REDACTED_PHONE]" in res.scrubbed_text
    assert "555-123-4567" not in res.scrubbed_text
    assert "PHONE" in res.redaction_types


def test_pii_scrubber_api_keys():
    scrubber = RegexPIIScrubber()
    text = "Leaked tokens: sk-abcdef1234567890abcdef123456 and ghp_12345678901234567890."
    res = scrubber.scrub(text)
    assert "[REDACTED_API_KEY]" in res.scrubbed_text
    assert "sk-abcdef1234567890abcdef123456" not in res.scrubbed_text
    assert "ghp_12345678901234567890" not in res.scrubbed_text
    assert "API_KEY" in res.redaction_types


def test_pii_scrubber_false_positives():
    scrubber = RegexPIIScrubber()
    text = "Software version 1.2.3 was deployed at a cost of $500.00 with 100 items."
    res = scrubber.scrub(text)
    assert res.redactions_count == 0
    assert res.scrubbed_text == text


def test_pii_scrubber_deterministic_repeated_runs():
    scrubber = RegexPIIScrubber()
    text = "User john.doe@example.com with phone 555-019-2834 has token sk-12345678901234567890."
    res1 = scrubber.scrub(text)
    res2 = scrubber.scrub(text)
    assert res1.scrubbed_text == res2.scrubbed_text
    assert res1.redactions_count == res2.redactions_count
