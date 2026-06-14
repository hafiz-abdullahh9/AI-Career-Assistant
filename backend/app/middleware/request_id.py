"""
Request ID middleware.

Attaches a unique trace_id to every incoming request and injects it into:
  1. structlog context (all log lines during the request carry this ID)
  2. Response header: X-Request-ID

This enables correlating all log lines for a single request in Datadog / Kibana.
"""
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Generates or propagates a Request ID for every HTTP request.

    If the client sends X-Request-ID: <id>, that ID is reused (useful for
    end-to-end tracing from the orchestrator). Otherwise a new UUID is generated.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID or generate a new one
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())

        # Bind to structlog context — all logs in this request will carry this
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=request_id)

        # Attach to request state for use in route handlers
        request.state.trace_id = request_id

        response = await call_next(request)

        # Echo the ID back in the response
        response.headers[self.HEADER_NAME] = request_id

        return response
