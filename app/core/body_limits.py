import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


MAX_JSON_BODY_BYTES = 1024 * 1024
MAX_IMPORT_BODY_BYTES = 2 * 1024 * 1024 + 64 * 1024


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = (
            MAX_IMPORT_BODY_BYTES
            if scope.get("path") == "/timetable/import"
            else MAX_JSON_BODY_BYTES
        )
        content_length = next(
            (
                value for key, value in scope.get("headers", [])
                if key.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return

        messages: list[Message] = []
        total_size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            total_size += len(message.get("body", b""))
            if total_size > limit:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps({"detail": "Request body is too large."}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
