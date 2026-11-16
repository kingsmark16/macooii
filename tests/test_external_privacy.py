import pytest

from macooii.privacy import TaskContext
from macooii.tools import ToolRegistry


class NeverBrowse:
    def search(self, *args):
        pytest.fail("Declined personal context reached a search engine")

    def read(self, *args):
        pytest.fail("Declined personal context reached a website")


def test_private_context_cannot_escape_through_search_or_url(store):
    registry = ToolRegistry(store, NeverBrowse())
    task = TaskContext(lambda *args: "decline", private_sources_used=True)
    with pytest.raises(PermissionError):
        registry.execute("search_web", {"query": "private secret"}, task)
    with pytest.raises(PermissionError):
        registry.execute("read_web", {"url": "https://example.com/?private=secret"}, task)


def test_permission_is_bound_to_recipient():
    calls = []
    task = TaskContext(lambda label, text: calls.append(label) or "approve")
    task.cloud_context("Source", "private")
    task.external_context("Bing", "Source", "private")
    assert len(calls) == 2
