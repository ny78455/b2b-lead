import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.suppression import is_suppressed, add_to_suppression, SuppressionError
from backend.models import SuppressionEntry


@pytest.mark.asyncio
async def test_add_to_suppression():
    db_mock = AsyncMock()
    
    # Simulate not found then add
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.side_effect = [None, SuppressionEntry(email="test@example.com")]
    db_mock.execute.return_value = result_mock
    
    entry = await add_to_suppression("test@example.com", "unsubscribe", db_mock)
    assert entry is not None
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_suppressed_true():
    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = SuppressionEntry(email="test@example.com")
    db_mock.execute.return_value = result_mock
    
    assert await is_suppressed("test@example.com", db_mock) is True


@pytest.mark.asyncio
async def test_is_suppressed_false():
    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_mock.execute.return_value = result_mock
    
    assert await is_suppressed("test@example.com", db_mock) is False
