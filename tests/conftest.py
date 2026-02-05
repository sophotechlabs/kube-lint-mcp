import pytest

from kube_lint_mcp import server


@pytest.fixture(autouse=True)
def reset_selected_context():
    """Reset server context state between tests."""
    server._selected_context = None
    yield
    server._selected_context = None
