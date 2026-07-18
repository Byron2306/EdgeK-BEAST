"""Fail-closed ASGI path boundary for the dedicated Commons service."""
from __future__ import annotations

import json
from typing import Any, Iterable


DEFAULT_COMMONS_PREFIXES = (
    "/edgek/commons",
    "/edgek/control-plane/commons",
    "/edgek/meta-tool-commons",
    "/edgek/federated-commons",
    "/edgek/proof-local",
    "/health",
    "/beast-assets",
)


class CommonsPathBoundary:
    """Expose the Commons UI root and explicitly owned route families only."""

    def __init__(
        self,
        application: Any,
        *,
        allowed_prefixes: Iterable[str] = DEFAULT_COMMONS_PREFIXES,
        allow_root: bool = True,
    ) -> None:
        self.application = application
        self.allowed_prefixes = tuple(str(item) for item in allowed_prefixes)
        self.allow_root = bool(allow_root)

    def permits(self, path: str) -> bool:
        return (self.allow_root and path == "/") or any(
            path.startswith(prefix) for prefix in self.allowed_prefixes
        )

    async def __call__(self, scope, receive, send) -> None:
        scope_type = scope.get("type")
        if scope_type in {"http", "websocket"}:
            path = str(scope.get("path") or "")
            if not self.permits(path):
                if scope_type == "websocket":
                    await send(
                        {
                            "type": "websocket.close",
                            "code": 1008,
                            "reason": "Commons service path boundary",
                        }
                    )
                    return
                body = json.dumps(
                    {"detail": "route is outside the dedicated Commons service boundary"}
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.application(scope, receive, send)
