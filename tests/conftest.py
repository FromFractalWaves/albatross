import pytest
from httpx import AsyncClient, ASGITransport

from api.main import app


@pytest.fixture
def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
