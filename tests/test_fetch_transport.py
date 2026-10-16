from datetime import datetime, UTC
import httpx
from bgbench.broker import BrokerItem
from bgbench.fetch import _fetch_one


def test_routeviews_connect_failure_retries_same_archive_over_tls(tmp_path, monkeypatch):
    monkeypatch.setattr('bgbench.fetch.time.sleep', lambda _: None)
    original = 'http://archive.routeviews.org/route-views3/bgpdata/2024.01/UPDATES/updates.20240101.0000.bz2'
    seen = []
    def respond(request):
        seen.append(str(request.url))
        if request.url.scheme == 'http':
            raise httpx.ConnectError('No route to host', request=request)
        return httpx.Response(200, content=b'archive')
    item = BrokerItem('route-views3', 'updates', datetime(2024,1,1,tzinfo=UTC), datetime(2024,1,1,0,15,tzinfo=UTC), original, 7, 7)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = _fetch_one(client, item, tmp_path, retries=2)
    assert seen == [original, original.replace('http:', 'https:', 1)]
    assert result.item.url == original
    assert result.transport_url == seen[-1]
    assert result.path.read_bytes() == b'archive'
