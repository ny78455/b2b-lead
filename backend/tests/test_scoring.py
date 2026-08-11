from backend.services.scoring import _compute_purchase_score
from backend.models import Company

def test_purchase_score_ai_hiring():
    company = Company(tech_stack_hints="React, Node.js, Machine Learning, AWS", rag_score=0)
    score = _compute_purchase_score(company)
    assert score == 20

def test_purchase_score_rag_high():
    company = Company(rag_score=80)
    score = _compute_purchase_score(company)
    assert score == 20

def test_purchase_score_llm_tools():
    company = Company(tech_stack_hints="OpenAI, Langchain", rag_score=0)
    score = _compute_purchase_score(company)
    assert score == 15

def test_purchase_score_support():
    company = Company(summary="We provide 24/7 customer support via our help center.", rag_score=0)
    score = _compute_purchase_score(company)
    assert score == 15

def test_purchase_score_size():
    company = Company(employees_estimate="51-200", rag_score=0)
    score = _compute_purchase_score(company)
    assert score == 15

def test_purchase_score_industry():
    company = Company(industry="Financial Services", rag_score=0)
    score = _compute_purchase_score(company)
    assert score == 15

def test_purchase_score_combined():
    company = Company(
        tech_stack_hints="Machine learning and langchain",
        summary="A knowledge base for medical professionals.",
        industry="Healthcare",
        employees_estimate="11-50",
        rag_score=90
    )
    score = _compute_purchase_score(company)
    # 20 (ai) + 20 (rag) + 15 (llm) + 15 (docs) + 15 (size) + 15 (industry) = 100
    assert score == 100
