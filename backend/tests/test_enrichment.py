import pytest
from unittest.mock import patch, AsyncMock
from backend.services.enrichment import enrich_company, _is_scraping_allowed
from backend.models import Company

def test_is_scraping_allowed_blocked():
    with patch('backend.services.enrichment.RobotFileParser') as MockRP:
        mock_rp_instance = MockRP.return_value
        mock_rp_instance.can_fetch.return_value = False
        assert _is_scraping_allowed("https://example.com") is False

def test_is_scraping_allowed_permitted():
    with patch('backend.services.enrichment.RobotFileParser') as MockRP:
        mock_rp_instance = MockRP.return_value
        mock_rp_instance.can_fetch.return_value = True
        assert _is_scraping_allowed("https://example.com") is True

@pytest.mark.asyncio
async def test_enrich_company_robots_txt_disallowed():
    db_mock = AsyncMock()
    company = Company(id="00000000-0000-0000-0000-000000000000", website="example.com")
    db_mock.execute.return_value.scalar_one_or_none.return_value = company

    with patch('backend.services.enrichment._is_scraping_allowed', return_value=False):
        res = await enrich_company(str(company.id), db_mock)
        assert res["status"] == "failed"
        assert "robots.txt" in res["message"]
        assert company.enrichment_status == "failed"
        db_mock.commit.assert_called_once()
