# kube-lint-mcp

[![CI](https://github.com/sophotechlabs/kube-lint-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sophotechlabs/kube-lint-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/sophotechlabs/kube-lint-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/sophotechlabs/kube-lint-mcp)
[![PyPI](https://img.shields.io/pypi/v/kube-lint-mcp.svg)](https://pypi.org/project/kube-lint-mcp/)
[![Docker](https://ghcr-badge.egpl.dev/sophotechlabs/kube-lint-mcp/latest_tag?trim=major&label=docker)](https://github.com/sophotechlabs/kube-lint-mcp/pkgs/container/kube-lint-mcp)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

MCP server that validates Kubernetes manifests and Helm charts with kubectl dry-run before you commit — preventing deployment and GitOps reconciliation failures.

Works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Claude Desktop](https://claude.ai/download), and any [MCP-compatible](https://modelcontextprotocol.io) client.

## How it works

```
You: "Validate the flux manifests in ./k8s/infrastructure/"

Claude: calls list_kube_contexts → presents list → you confirm "staging"
        calls select_kube_context → flux_dryrun

  FluxCD Dry-Run Validation
  Context: staging
  ================================================
  File: infrastructure/redis.yaml
    Client dry-run: PASS
    Server dry-run: PASS

  File: infrastructure/postgres.yaml
    Client dry-run: PASS
    Server dry-run: FAIL
      Error: namespace "db" not found
  ================================================
  Summary: 1 passed, 1 failed

  DO NOT COMMIT - Fix errors first!
```

No flags, no CLI args — the AI agent picks the right tool automatically.

## Prerequisites

- Python 3.12+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) configured with cluster access
- [helm](https://helm.sh/docs/intro/install/) (for Helm chart validation)
- [flux](https://fluxcd.io/flux/installation/) (for Flux operations)

## Installation

### pip (requires CLI tools installed separately)

```bash
pip install kube-lint-mcp
```

### Docker (batteries included)

The Docker image ships with kubectl, helm, flux, and kubeconform — no local installs needed.

```bash
docker pull ghcr.io/sophotechlabs/kube-lint-mcp:latest
```

> **Note**: If your kubeconfig uses external auth plugins (e.g. `gke-gcloud-auth-plugin`, `aws-iam-authenticator`), those binaries are not included in the image. Use the pip install method for those clusters, or embed tokens directly in your kubeconfig.

## Configuration

### Claude Code (pip)

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "kube-lint": {
      "command": "python",
      "args": ["-m", "kube_lint_mcp"]
    }
  }
}
```

### Claude Code (Docker)

```json
{
  "mcpServers": {
    "kube-lint": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "${HOME}:${HOME}:ro",
        "-e", "KUBECONFIG=${HOME}/.kube/config",
        "ghcr.io/sophotechlabs/kube-lint-mcp:latest"
      ]
    }
  }
}
```

The `$HOME:$HOME:ro` mount preserves absolute paths that MCP clients send to the server. The read-only flag ensures the container cannot modify your files.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "kube-lint": {
      "command": "python",
      "args": ["-m", "kube_lint_mcp"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `select_kube_context` | Pick a cluster context (held in memory, no kubeconfig mutation). **Call first.** |
| `list_kube_contexts` | Show available kubectl contexts and which is selected |
| `flux_dryrun` | Validate FluxCD YAML with client + server dry-run |
| `kustomize_dryrun` | Build and dry-run a Kustomize overlay end-to-end |
| `helm_dryrun` | Lint, render, and dry-run a Helm chart end-to-end |
| `flux_check` | Verify Flux installation health |
| `flux_status` | Show Flux reconciliation status across namespaces |

### Workflow

1. `list_kube_contexts` — see available clusters
2. `select_kube_context` — target a cluster (in-memory only, never mutates kubeconfig)
3. `flux_dryrun`, `kustomize_dryrun`, or `helm_dryrun` — validate before committing
4. Only commit when all checks pass

### Safety

The server **never mutates your kubeconfig**. Context is held in memory and passed via `--context` flag on every subprocess call. This is a deliberate safety choice for agentic use — the AI cannot accidentally switch your global kubectl context.

## Development

```bash
pip install -e ".[dev]"
make test    # 126 tests, 100% coverage
make lint    # flake8
```

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make sure `make test` and `make lint` pass
4. Open a PR

## License

[MIT](LICENSE)

---

If this tool saves you from a bad deploy, consider [sponsoring](https://github.com/sponsors/sophotechlabs).
