"""Request ID middleware and logging context."""

import logging
import re
from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import Response

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class RequestIdMiddleware:
    """Preserve a valid caller request ID or generate a UUID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        incoming_id = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming_id if _VALID_REQUEST_ID.fullmatch(incoming_id) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        try:
            async def send_with_request_id(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_headers = list(message.get("headers", []))
                    response_headers.append((b"x-request-id", request_id.encode("ascii")))
                    message = {**message, "headers": response_headers}
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_context.reset(token)
