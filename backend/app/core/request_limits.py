"""Bound request bodies before multipart parsing can spool files to disk."""
from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse

from app.core.config import get_settings


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        # Allow multipart headers and form fields in addition to the file limit.
        limit = get_settings().max_upload_bytes + 1024 * 1024
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > limit
            except ValueError:
                return await JSONResponse({"detail": "INVALID_CONTENT_LENGTH"}, 400)(scope, receive, send)
            if too_large:
                return await JSONResponse({"detail": "REQUEST_TOO_LARGE"}, 413)(scope, receive, send)
        # Count actual bytes too: Content-Length can be absent or inaccurate.
        # Buffering is bounded and always cleaned, including on disconnect.
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > limit:
                    return await JSONResponse({"detail": "REQUEST_TOO_LARGE"}, 413)(scope, receive, send)
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)
            remaining = size
            replayed = False

            async def replay():
                nonlocal remaining, replayed
                if not replayed:
                    chunk = body.read(64 * 1024)
                    remaining -= len(chunk)
                    replayed = remaining == 0
                    return {"type": "http.request", "body": chunk, "more_body": remaining > 0}
                return await receive()

            await self.app(scope, replay, send)
