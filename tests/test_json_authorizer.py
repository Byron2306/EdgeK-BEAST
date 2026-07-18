from app.kernel.integration.arda_metatron_bridge import JsonHttpAuthorizer


def test_http_authorizer_fails_closed_on_unreachable_endpoint():
    assert JsonHttpAuthorizer("http://127.0.0.1:1/authorize", timeout=0.01)({"crystal_id": "x"}) is False

