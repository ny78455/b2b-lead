import pytest
from unittest.mock import AsyncMock, patch

from backend.services.suppression import is_suppressed, add_to_suppression, SuppressionError
from backend.models import SuppressionEntry


@pytest.mark.asyncio
async def test_add_to_suppression():
    db_mock = AsyncMock()
    
    # Simulate not found then add
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [None, SuppressionEntry(email="test@example.com")]
    
    entry = await add_to_suppression("test@example.com", "unsubscribe", db_mock)
    assert entry is not None
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_suppressed_true():
    db_mock = AsyncMock()
    db_mock.execute.return_value.scalar_one_or_none.return_value = SuppressionEntry(email="test@example.com")
    
    assert await is_suppressed("test@example.com", db_mock) is True


@pytest.mark.asyncio
async def test_is_suppressed_false():
    db_mock = AsyncMock()
    db_mock.execute.return_value.scalar_one_or_none.return_value = None
    
    assert await is_suppressed("test@example.com", db_mock) is False
