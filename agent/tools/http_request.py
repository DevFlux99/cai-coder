import requests
import json
from typing import Optional, Dict, Any

from langchain_core.tools import tool


def _http_request_impl(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    HTTP request implementation function

    Args:
        url: Request URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Request headers dict
        params: URL query parameters
        data: Form data
        json_data: JSON data
        timeout: Timeout in seconds

    Returns:
        Dict containing response information
    """
    try:
        # Normalize method to uppercase
        method = method.upper()

        # Default headers
        if headers is None:
            headers = {}

        # Automatically set Content-Type for JSON data
        if json_data is not None and 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        # Send request
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json_data,
            timeout=timeout
        )

        # Try to parse JSON response
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            response_json = None

        # Return structured response information
        return {
            "success": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.text,
            "json": response_json,
            "url": response.url,
            "elapsed_time": response.elapsed.total_seconds()
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@tool
def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    HTTP request tool

    Args:
        url: Request URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Request headers dict
        params: URL query parameters
        data: Form data
        json_data: JSON data
        timeout: Timeout in seconds

    Returns:
        Dict containing response information
    """
    return _http_request_impl(
        url=url,
        method=method,
        headers=headers,
        params=params,
        data=data,
        json_data=json_data,
        timeout=timeout
    )


@tool
def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Convenience method for sending GET requests"""
    return _http_request_impl(
        url=url,
        method="GET",
        headers=headers,
        params=params,
        timeout=timeout
    )


@tool
def http_post(
    url: str,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Convenience method for sending POST requests"""
    return _http_request_impl(
        url=url,
        method="POST",
        headers=headers,
        data=data,
        json_data=json_data,
        timeout=timeout
    )