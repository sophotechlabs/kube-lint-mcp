"""Allow running with: python -m kube_lint_mcp"""  # pragma: no cover

import asyncio  # pragma: no cover

from kube_lint_mcp.server import main  # pragma: no cover

asyncio.run(main())  # pragma: no cover
