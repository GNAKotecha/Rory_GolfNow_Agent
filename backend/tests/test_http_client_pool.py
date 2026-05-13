"""Tests for HTTP client pool reuse (Task C1)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.ollama import (
    OllamaClient,
    OllamaHTTPClientPool,
    startup_ollama_client_pool,
    shutdown_ollama_client_pool,
)


class TestOllamaHTTPClientPool:
    """Tests for OllamaHTTPClientPool singleton and lifecycle."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        OllamaHTTPClientPool._instance = None
        yield
        OllamaHTTPClientPool._instance = None

    def test_get_instance_returns_singleton(self):
        """get_instance() should return the same instance."""
        pool1 = OllamaHTTPClientPool.get_instance()
        pool2 = OllamaHTTPClientPool.get_instance()
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_startup_creates_client(self):
        """startup() should create an HTTP client."""
        pool = OllamaHTTPClientPool.get_instance()
        assert pool._client is None
        
        await pool.startup()
        
        assert pool._client is not None
        assert not pool._client.is_closed
        
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self):
        """shutdown() should close the HTTP client."""
        pool = OllamaHTTPClientPool.get_instance()
        await pool.startup()
        client = pool._client
        
        await pool.shutdown()
        
        assert pool._client is None
        assert client.is_closed

    @pytest.mark.asyncio
    async def test_get_client_auto_initializes(self):
        """get_client() should auto-initialize if not started."""
        pool = OllamaHTTPClientPool.get_instance()
        assert pool._client is None
        
        client = await pool.get_client()
        
        assert client is not None
        assert not client.is_closed
        
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_client_reuses_connection(self):
        """get_client() should return the same client instance."""
        pool = OllamaHTTPClientPool.get_instance()
        await pool.startup()
        
        client1 = await pool.get_client()
        client2 = await pool.get_client()
        
        assert client1 is client2
        
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_track_requests(self):
        """Metrics should track request count and connection reuse."""
        pool = OllamaHTTPClientPool.get_instance()
        await pool.startup()
        
        # First request
        await pool.get_client()
        metrics1 = pool.get_metrics()
        assert metrics1["total_requests"] == 1
        assert metrics1["connection_reuses"] == 0
        
        # Second request (reuse)
        await pool.get_client()
        metrics2 = pool.get_metrics()
        assert metrics2["total_requests"] == 2
        assert metrics2["connection_reuses"] == 1
        
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_show_active_state(self):
        """Metrics should reflect active/inactive state."""
        pool = OllamaHTTPClientPool.get_instance()
        
        metrics_before = pool.get_metrics()
        assert metrics_before["is_active"] is False
        
        await pool.startup()
        metrics_active = pool.get_metrics()
        assert metrics_active["is_active"] is True
        
        await pool.shutdown()
        metrics_after = pool.get_metrics()
        assert metrics_after["is_active"] is False

    @pytest.mark.asyncio
    async def test_concurrent_get_client_no_race_condition(self):
        """Concurrent get_client() calls should not create multiple clients."""
        pool = OllamaHTTPClientPool.get_instance()
        
        # Ensure pool is not initialized
        assert pool._client is None
        
        # Launch multiple concurrent get_client() calls
        async def get_client_task():
            return await pool.get_client()
        
        # Create 10 concurrent tasks all trying to initialize
        tasks = [get_client_task() for _ in range(10)]
        clients = await asyncio.gather(*tasks)
        
        # All clients should be the same instance (no race condition)
        first_client = clients[0]
        for client in clients[1:]:
            assert client is first_client, "Race condition: multiple clients created"
        
        # Verify only one client was created
        assert pool._client is first_client
        
        await pool.shutdown()


class TestOllamaClientWithPool:
    """Tests for OllamaClient using the shared pool."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        OllamaHTTPClientPool._instance = None
        yield
        OllamaHTTPClientPool._instance = None

    @pytest.mark.asyncio
    async def test_ollama_client_uses_shared_pool(self):
        """OllamaClient should use the shared pool by default."""
        pool = OllamaHTTPClientPool.get_instance()
        await pool.startup()
        
        client1 = OllamaClient()
        client2 = OllamaClient()
        
        # Both should use the same pool
        pool_client = await pool.get_client()
        internal1 = await client1._get_client()
        internal2 = await client2._get_client()
        
        assert internal1 is pool_client
        assert internal2 is pool_client
        
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_ollama_client_accepts_explicit_client(self):
        """OllamaClient should use explicit client if provided."""
        explicit_client = httpx.AsyncClient()
        
        client = OllamaClient(http_client=explicit_client)
        internal = await client._get_client()
        
        assert internal is explicit_client
        
        await explicit_client.aclose()

    @pytest.mark.asyncio
    async def test_check_connection_uses_shared_client(self):
        """check_connection should use the shared pool."""
        pool = OllamaHTTPClientPool.get_instance()
        await pool.startup()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(pool._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            client = OllamaClient()
            result = await client.check_connection()
            
            assert result is True
            mock_get.assert_called_once()
        
        await pool.shutdown()


class TestLifecycleFunctions:
    """Tests for module-level lifecycle functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        OllamaHTTPClientPool._instance = None
        yield
        OllamaHTTPClientPool._instance = None

    @pytest.mark.asyncio
    async def test_startup_ollama_client_pool(self):
        """startup_ollama_client_pool should initialize the pool."""
        pool = OllamaHTTPClientPool.get_instance()
        assert pool._client is None
        
        await startup_ollama_client_pool()
        
        assert pool._client is not None
        
        await shutdown_ollama_client_pool()

    @pytest.mark.asyncio
    async def test_shutdown_ollama_client_pool(self):
        """shutdown_ollama_client_pool should close the pool."""
        await startup_ollama_client_pool()
        pool = OllamaHTTPClientPool.get_instance()
        
        assert pool._client is not None
        
        await shutdown_ollama_client_pool()
        
        assert pool._client is None
