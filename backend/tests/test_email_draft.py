import pytest
from unittest.mock import patch, AsyncMock
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
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [company, contact]
    
    # Mock LLM to return dictionary
    with patch('backend.services.llm.draft_email', return_value={"html": "<p>Hi John,</p><p>Buy our stuff.</p>", "draft_source": "gemini"}):
        res = await generate_draft(str(company.id), db_mock)
        
        assert res["status"] == "done"
        
        # Check that the campaign was created and added to the session
        added_campaign = db_mock.add.call_args[0][0]
        assert "{{unsubscribe_link}}" in added_campaign.draft_html
