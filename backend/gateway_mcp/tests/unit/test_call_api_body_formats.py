"""
Unit tests for call_api tool with body_format parameter support.

Tests the new body_format parameter supporting:
- json (default): JSON-encoded request body
- form: URL-encoded form data
- raw: Raw string body
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_mcp.core.errors import ToolExecutionError
from gateway_mcp.tools.base import Environment, ToolContext
from gateway_mcp.tools.teesheet.handlers import call_api_handler
from gateway_mcp.tools.teesheet.schemas import CallApiInput, CallApiOutput


@pytest.fixture
def context():
    """Tool context for tests."""
    return ToolContext(
        user_id=1,
        correlation_id="test-corr-123",
        audit_id="test-audit-123",
        environment=Environment.LOCAL,
    )


class TestCallApiBodyFormats:
    """Tests for call_api with different body_format options."""

    @pytest.mark.asyncio
    async def test_json_format_default(self, context):
        """Test default json format (backward compatible)."""
        input = CallApiInput(
            method="POST",
            path="/api/v3/clubs/test/bookings",
            club_id="test",
            body={"key": "value", "number": 123},
            # body_format defaults to "json"
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.text = '{"success": true}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify json parameter was used (not content)
            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("json") == {"key": "value", "number": 123}
            assert "content" not in call_args.kwargs or call_args.kwargs.get("content") is None

            assert result.status == 200
            assert result.body == {"success": True}

    @pytest.mark.asyncio
    async def test_json_format_explicit(self, context):
        """Test explicit json format."""
        input = CallApiInput(
            method="POST",
            path="/api/v3/clubs/test/bookings",
            club_id="test",
            body={"email": "test@example.com", "name": "John"},
            body_format="json",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": 123, "email": "test@example.com"}
            mock_response.headers = {}
            mock_response.text = '{"id": 123}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("json") == {"email": "test@example.com", "name": "John"}
            assert result.status == 201

    @pytest.mark.asyncio
    async def test_form_format(self, context):
        """Test form (application/x-www-form-urlencoded) format."""
        input = CallApiInput(
            method="PATCH",
            path="/api/v2/user",
            club_id="test",
            body={"email": "test@example.com", "first_name": "John", "last_name": "Doe"},
            body_format="form",
            query={"user": "18"},
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "updated"}
            mock_response.headers = {}
            mock_response.text = '{"status": "updated"}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify content parameter was used (not json)
            call_args = mock_client.request.call_args
            assert "content" in call_args.kwargs
            assert call_args.kwargs.get("json") is None

            # Verify body was URL-encoded
            encoded_body = call_args.kwargs.get("content")
            assert "email=test%40example.com" in encoded_body
            assert "first_name=John" in encoded_body
            assert "last_name=Doe" in encoded_body

            # Verify Content-Type header was set
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("Content-Type") == "application/x-www-form-urlencoded"

            assert result.status == 200

    @pytest.mark.asyncio
    async def test_raw_format(self, context):
        """Test raw format (string body as-is)."""
        xml_body = '<?xml version="1.0"?><root><key>value</key></root>'
        input = CallApiInput(
            method="POST",
            path="/api/v3/xml-endpoint",
            club_id="test",
            body=xml_body,
            body_format="raw",
            headers={"Content-Type": "application/xml"},
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Not JSON", "", 0)
            mock_response.headers = {}
            mock_response.text = "<success/>"

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify content parameter was used with raw string
            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("content") == xml_body
            assert call_args.kwargs.get("json") is None

            # User's headers should be preserved
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("Content-Type") == "application/xml"

            assert result.status == 200
            assert result.body == "<success/>"

    @pytest.mark.asyncio
    async def test_form_requires_dict_body(self, context):
        """Test that form format requires dict body, not string."""
        from pydantic import ValidationError

        # Validation should fail at Pydantic level
        with pytest.raises(ValidationError, match="form.*requires body to be a dict"):
            CallApiInput(
                method="POST",
                path="/api/endpoint",
                club_id="test",
                body="string_body",  # Invalid: form requires dict
                body_format="form",
            )

    @pytest.mark.asyncio
    async def test_raw_requires_string_body(self, context):
        """Test that raw format requires string body, not dict."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="raw.*requires body to be a string"):
            CallApiInput(
                method="POST",
                path="/api/endpoint",
                club_id="test",
                body={"key": "value"},  # Invalid: raw requires string
                body_format="raw",
            )

    @pytest.mark.asyncio
    async def test_form_with_special_characters(self, context):
        """Test form encoding properly handles special characters."""
        input = CallApiInput(
            method="POST",
            path="/api/endpoint",
            club_id="test",
            body={
                "email": "john+test@example.com",
                "message": "Hello World! @#$%",
                "utf8": "café",
            },
            body_format="form",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.headers = {}
            mock_response.text = "{}"

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify proper URL encoding
            call_args = mock_client.request.call_args
            encoded_body = call_args.kwargs.get("content")

            # Special characters should be encoded
            assert "email=john%2Btest%40example.com" in encoded_body
            assert "message=Hello+World%21+%40%23%24%25" in encoded_body
            assert "utf8=caf%C3%A9" in encoded_body  # UTF-8 encoded

    @pytest.mark.asyncio
    async def test_get_request_ignores_body_format(self, context):
        """Test that GET requests ignore body and body_format."""
        input = CallApiInput(
            method="GET",
            path="/api/clubs",
            club_id="test",
            body={"should": "be ignored"},  # Will be ignored for GET
            body_format="form",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"clubs": []}
            mock_response.headers = {}
            mock_response.text = '{"clubs": []}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify neither json nor content were sent
            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("json") is None
            assert call_args.kwargs.get("content") is None

            assert result.status == 200

    @pytest.mark.asyncio
    async def test_backward_compatibility_no_body_format_specified(self, context):
        """Test backward compatibility: old code without body_format still works."""
        # Simulate old code that doesn't specify body_format
        input = CallApiInput(
            method="POST",
            path="/api/endpoint",
            club_id="test",
            body={"key": "value"},
            # No body_format specified - should default to "json"
        )

        assert input.body_format == "json"

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "success"}
            mock_response.headers = {}
            mock_response.text = '{"result": "success"}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify json parameter was used (default behavior)
            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("json") == {"key": "value"}

            assert result.status == 200

    @pytest.mark.asyncio
    async def test_form_format_with_values(self, context):
        """Test form format with non-empty values."""
        input = CallApiInput(
            method="POST",
            path="/api/endpoint",
            club_id="test",
            body={"key": "value", "field": "data"},
            body_format="form",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_response.headers = {}
            mock_response.text = '{"success": true}'

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify form encoding is used
            call_args = mock_client.request.call_args
            encoded_body = call_args.kwargs.get("content")
            assert "key=value" in encoded_body
            assert "field=data" in encoded_body
            assert result.status == 200

    @pytest.mark.asyncio
    async def test_raw_format_with_content(self, context):
        """Test raw format with string content."""
        input = CallApiInput(
            method="POST",
            path="/api/endpoint",
            club_id="test",
            body="<data>content</data>",
            body_format="raw",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Not JSON", "", 0)
            mock_response.headers = {}
            mock_response.text = "<success/>"

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            result = await call_api_handler(input, context)

            # Verify raw string is sent as-is
            call_args = mock_client.request.call_args
            assert call_args.kwargs.get("content") == "<data>content</data>"
            assert result.status == 200

    @pytest.mark.asyncio
    async def test_connect_error_handling(self, context):
        """Test that httpx.ConnectError is caught and converted to UpstreamError."""
        import httpx
        from gateway_mcp.core.errors import UpstreamError, ErrorCode

        input = CallApiInput(
            method="GET",
            path="/api/endpoint",
            club_id="test",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            with pytest.raises(UpstreamError) as exc_info:
                await call_api_handler(input, context)

            # Verify error is UpstreamError with correct code
            error = exc_info.value
            assert error.code == ErrorCode.UPSTREAM_ERROR.value
            assert "Cannot connect to Teesheet" in error.message

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self, context):
        """Test that httpx.TimeoutException is caught and converted to UpstreamError."""
        import httpx
        from gateway_mcp.core.errors import UpstreamError, ErrorCode

        input = CallApiInput(
            method="GET",
            path="/api/endpoint",
            club_id="test",
        )

        with patch("gateway_mcp.tools.teesheet.handlers.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("Request timed out")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            with pytest.raises(UpstreamError) as exc_info:
                await call_api_handler(input, context)

            # Verify error is UpstreamError with correct code
            error = exc_info.value
            assert error.code == ErrorCode.UPSTREAM_ERROR.value
            assert "timed out" in error.message.lower()
