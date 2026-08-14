import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.services.email_draft import generate_draft
from backend.models import Company, Contact

@pytest.mark.asyncio
async def test_generate_draft_includes_unsubscribe():
    db_mock = AsyncMock()
    
    company = Company(
        id="00000000-0000-0000-0000-000000000000",
        name="Test Corp",
        persona_summary="A cool company."
    )
    contact = Contact(
        id="11111111-1111-1111-1111-111111111111",
        name="John",
        email="john@test.com"
    )
    
    # First execute returns company, second returns contact
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.side_effect = [company, contact]
    db_mock.execute.return_value = result_mock
    
    # Mock LLM to return dictionary
    with patch('backend.services.llm.draft_email', return_value={"html": "<p>Hi John,</p><p>Buy our stuff. {{unsubscribe_link}}</p>", "draft_source": "gemini"}):
        res = await generate_draft(str(company.id), db_mock)
        
        assert res["status"] == "done"
        
        # Check that the campaign was created and added to the session
        added_campaign = db_mock.add.call_args[0][0]
        assert "{{unsubscribe_link}}" in added_campaign.draft_html

from backend.services.enrichment import enrich_company
from backend.services.scoring import score_company
from backend.services.persona import build_persona

@pytest.mark.asyncio
async def test_pipeline_single_llm_call():
    db_mock = AsyncMock()
    
    company = Company(
        id="00000000-0000-0000-0000-000000000000",
        name="Test Corp",
        website="https://example.com",
    )
    contact = Contact(
        id="11111111-1111-1111-1111-111111111111",
        name="John",
        email="john@test.com"
    )
    
    # We need to simulate the DB returning the company in each step
    # enrich_company -> returns company
    # score_company -> returns company
    # build_persona -> returns company
    # generate_draft -> returns company, then contact
    
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.side_effect = [
        company, # enrich
        company, # score
        company, # persona
        company, contact # draft
    ]
    db_mock.execute.return_value = result_mock
    
    with patch('backend.services.enrichment._gather_site_data', return_value=(None, "A test company website mentioning AI and support.")):
        with patch('backend.services.llm._call_gemini', return_value="<p>Generated draft</p>") as mock_gemini:
            # 1. Enrich
            await enrich_company(str(company.id), db_mock)
            # 2. Score
            await score_company(str(company.id), db_mock)
            # 3. Persona
            await build_persona(str(company.id), db_mock)
            # 4. Draft
            await generate_draft(str(company.id), db_mock)
            
            # Assert exactly one outbound LLM call
            mock_gemini.assert_called_once()
