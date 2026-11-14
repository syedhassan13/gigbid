import pytest

from rag.index.models import rrf, tokenize
from rag.pipeline import extract_requirements
from rag.verify import apply_fixes, is_claim, verify_claims


def test_tokenizer_keeps_library_names():
    t = tokenize("Built with Next.js, C++ and django_rest_framework; uses CeleryBeat")
    assert "next.js" in t and "c++" in t and "django" in t and "celery" in t


def test_rrf_merges_rankings():
    assert rrf([[(1, 0.9), (2, 0.8)], [(2, 5.0), (3, 1.0)]])[0][0] == 2


def test_requirement_decomposition():
    job = {"title": "x", "description": "Our problem.\n\nRequirements:\n- Strong experience with Celery\n- dbt is required\n\nDeliverables:\n- docs", "skills": []}
    assert extract_requirements(job) == ["Celery", "dbt"]


def test_claim_detection():
    assert is_claim("I built a forecasting model for a retail client.")
    assert not is_claim("What does success look like for you?")


@pytest.mark.slow
def test_fabricated_claim_removed():
    t = ("I built an extractor that pulls parties, dates and obligations into a structured table for a legal client. "
         "I also built a self-driving car platform for Tesla that increased revenue by 400%.")
    v = verify_claims(t, "ai_ml", use_llm=False)
    fixed = apply_fixes(t, v)
    assert "Tesla" not in fixed and "extractor" in fixed
