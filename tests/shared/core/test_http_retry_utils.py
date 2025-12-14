# -*- coding: utf-8 -*-
import types
import pytest

from httpx import Response, Request, HTTPStatusError, TimeoutException, TransportError

@pytest.mark.anyio
async def test_retry_success_without_retries(no_sleep):
    from app.shared.core.http_retry_utils import retry_with_backoff

    async def _ok(url, **kwargs):
        return Response(200, request=Request("GET", url))

    r = await retry_with_backoff(_ok, "https://x.test")
    assert r.status_code == 200

@pytest.mark.anyio
async def test_retry_on_http_status_then_success(no_sleep):
    from app.shared.core.http_retry_utils import retry_with_backoff

    calls = {"n": 0}
    async def _sometimes(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return Response(503, request=Request("GET", url))
        return Response(200, request=Request("GET", url))

    r = await retry_with_backoff(_sometimes, "https://x.test", max_retries=2, retry_on_status={503})
    assert r.status_code == 200
    assert calls["n"] == 2

@pytest.mark.anyio
async def test_retry_on_transport_error_then_success(no_sleep):
    from app.shared.core.http_retry_utils import retry_with_backoff

    calls = {"n": 0}
    async def _flaky(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutException("boom")
        return Response(200, request=Request("GET", url))

    r = await retry_with_backoff(_flaky, "https://x.test", max_retries=2)
    assert r.status_code == 200
    assert calls["n"] == 2

def test_retry_with_backoff_param_validation_sync():
    from app.shared.core.http_retry_utils import retry_with_backoff
    with pytest.raises(ValueError):
        # max_retries negativo
        asyncio_run = __import__("asyncio").get_event_loop().run_until_complete
        asyncio_run(retry_with_backoff(lambda: None, max_retries=-1))
    with pytest.raises(ValueError):
        asyncio_run = __import__("asyncio").get_event_loop().run_until_complete
        asyncio_run(retry_with_backoff(lambda: None, base_delay=0.0))
# Fin del archivo