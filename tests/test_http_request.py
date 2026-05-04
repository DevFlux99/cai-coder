import pytest
from agent.tools.http_request import http_get, http_post


def test_http_get():
    """Test GET request"""
    # Test with httpbin.org
    result = http_get.invoke({"url": "https://httpbin.org/get"})
    assert result["success"] is True
    assert result["status_code"] == 200
    assert "json" in result
    assert result["json"]["url"] == "https://httpbin.org/get"


def test_http_post():
    """Test POST request"""
    # Test with httpbin.org
    test_data = {"name": "test", "value": 123}
    result = http_post.invoke({"url": "https://httpbin.org/post", "json_data": test_data})
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["json"]["json"] == test_data


def test_http_with_headers():
    """Test request with custom headers"""
    headers = {"User-Agent": "test-agent", "Accept": "application/json"}
    result = http_get.invoke({"url": "https://httpbin.org/headers", "headers": headers})
    assert result["success"] is True
    assert result["status_code"] == 200
    assert "headers" in result


def test_http_with_params():
    """Test request with query parameters"""
    params = {"param1": "value1", "param2": "value2"}
    result = http_get.invoke({"url": "https://httpbin.org/get", "params": params})
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["json"]["args"] == params


def test_http_error_handling():
    """Test error handling"""
    # Test with a non-existent URL
    result = http_get.invoke({"url": "https://nonexistent-domain-12345.com"})
    assert result["success"] is False
    assert "error" in result


def test_http_404_error():
    """Test 404 error"""
    result = http_get.invoke({"url": "https://httpbin.org/status/404"})
    assert result["success"] is True  # Request succeeded, but status code is 404
    assert result["status_code"] == 404