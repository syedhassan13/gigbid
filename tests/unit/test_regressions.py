"""Regression tests for bugs found during evaluation / demo recording."""
from agent.nodes.compliance import enforce
from agent.nodes.risk import assess
from agent.tracing import mask_pii

OK = {"payment_verified": True, "total_spent": 5000, "hires": 3}


def test_interview_slots_are_not_redacted_as_phone_numbers():
    v = enforce("I'm free at 2026-11-03 09:00 or 2026-11-04 11:00. Call me on +1 555 010 0222.", add_required=False)
    assert "2026-11-03 09:00" in v.text and "2026-11-04 11:00" in v.text and "555" not in v.text
    assert "2026-11-03 09:00" in mask_pii("slot 2026-11-03 09:00")


def test_channel_name_alone_is_not_off_platform():
    assert not assess({"id": "x", "title": "Creating a Telegram Bot for Excel reports", "description": "Build a Telegram bot."}, OK).is_scam
    assert assess({"id": "x", "title": "t", "description": "Contact me on Telegram @fast, payment through crypto."}, OK).is_scam


def test_required_statement_only_when_asked():
    assert "AI assistance" not in enforce("Thanks for the question, happy to help with the dashboard.", add_required=False).text
