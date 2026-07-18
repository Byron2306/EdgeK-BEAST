import asyncio
import json

from app.kernel.commons.service_boundary import CommonsPathBoundary


async def _invoke(boundary, path, scope_type="http"):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await boundary({"type": scope_type, "path": path}, receive, send)
    return sent


def test_commons_boundary_exposes_root_and_owned_routes_only():
    async def application(scope, _receive, send):
        body = scope["path"].encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})

    boundary = CommonsPathBoundary(application)
    assert boundary.permits("/")
    assert boundary.permits("/edgek/control-plane/commons")
    assert boundary.permits("/edgek/commons-spaces/registry")
    assert not boundary.permits("/edgek/control-plane/services")

    allowed = asyncio.run(_invoke(boundary, "/"))
    assert allowed[0]["status"] == 200
    denied = asyncio.run(_invoke(boundary, "/edgek/control-plane/services"))
    assert denied[0]["status"] == 404
    assert "outside" in json.loads(denied[1]["body"])["detail"]


def test_commons_boundary_policy_closes_unowned_websocket():
    async def application(_scope, _receive, _send):
        raise AssertionError("unowned route reached application")

    sent = asyncio.run(_invoke(CommonsPathBoundary(application), "/edgek/ws", "websocket"))
    assert sent == [
        {
            "type": "websocket.close",
            "code": 1008,
            "reason": "Commons service path boundary",
        }
    ]
