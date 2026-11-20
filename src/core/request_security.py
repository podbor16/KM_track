"""Helpers for security decisions based on the original client request."""

from fastapi import Request


def request_uses_https(request: Request) -> bool:
    """Use the scheme set by our reverse proxy, falling back to direct HTTP(S)."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
