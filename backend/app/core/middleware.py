"""
QuantX — ASGI middleware for request-size limits and response headers.

Both are plain ASGI wrappers (not ``BaseHTTPMiddleware``) so they add no task
per request and do not buffer streaming responses.
"""

from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLargeError(Exception):
    """Raised from ``receive`` once a request body passes the limit."""


class BodySizeLimitMiddleware:
    """Refuse request bodies larger than ``max_bytes``.

    The framework reads and parses the whole body before any route dependency
    runs, including authentication and rate limiting, so without a ceiling an
    anonymous caller decides how much memory and CPU each request costs. A
    declared ``Content-Length`` over the limit is refused before anything is
    read; a body that grows past the limit while streaming is cut off.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not response_started:
                await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = b'{"error":true,"message":"Request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    """Add conservative response headers to every API response.

    The API returns JSON, some of it credentials (token pairs). These headers
    stop a browser from sniffing a response into something executable, from
    framing it, and from keeping it in a shared cache.
    """

    _HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"cache-control", b"no-store"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[Any] = list(message.get("headers") or [])
                present = {name.lower() for name, _ in headers}
                headers.extend((name, value) for name, value in self._HEADERS if name not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
