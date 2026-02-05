# kube-lint-mcp

MCP server for Kubernetes manifest and Helm chart validation — validates manifests with kubectl dry-run before committing to prevent deployment and GitOps reconciliation failures.

## Prerequisites

- Python 3.12+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) configured with cluster access
- [helm](https://helm.sh/docs/intro/install/) (for Helm chart validation)
- [flux](https://fluxcd.io/flux/installation/) (for Flux operations)

## Installation

### From source

```bash
git clone https://github.com/sophotech/kube-lint-mcp.git
cd kube-lint-mcp
pip install -e ".[dev]"
```

## Configuration

### Claude Code

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

### `select_kube_context`

Select the Kubernetes context for all subsequent operations. **Must be called first.** Does not mutate global kubeconfig — context is held in memory only.

### `list_kube_contexts`

List available kubectl contexts and show which is currently selected.

### `flux_dryrun`

Validate FluxCD manifests with kubectl dry-run (client + server).

**Parameters:**
- `path` (required): Path to YAML file or directory

### `helm_dryrun`

Validate Helm chart by rendering and running kubectl dry-run (client + server).

**Parameters:**
- `chart_path` (required): Path to Helm chart directory
- `values_file` (optional): Path to values file
- `namespace` (optional): Namespace for rendering
- `release_name` (optional): Release name for helm template (default: "release-name")

### `flux_check`

Run `flux check` to verify Flux installation health.

### `flux_status`

Get Flux reconciliation status for all resources.

## Workflow

1. Call `list_kube_contexts` to see available clusters
2. Call `select_kube_context` to target a cluster (held in memory only — no kubeconfig mutation)
3. Use `flux_dryrun` or `helm_dryrun` to validate before committing
4. Only commit when all checks pass

## Development

```bash
pip install -e ".[dev]"
make test
```
