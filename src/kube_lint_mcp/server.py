"""MCP server for Kubernetes manifest validation."""

import asyncio
import logging
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:  # pragma: no cover
    print(
        "Error: MCP SDK not installed. Install with: pip install mcp", file=sys.stderr
    )
    sys.exit(1)

from kube_lint_mcp import argocd_lint, flux_lint, formatters, helm_lint, kubeconform_lint, kustomize_lint, yaml_lint

logger = logging.getLogger(__name__)

# Create MCP server instance
app = Server("kube-lint-mcp")

# In-memory context selection — no global kubeconfig mutation
_selected_context: str | None = None
_contexts_listed_at: float | None = None  # timestamp when list_kube_contexts was called

# Minimum seconds between list_kube_contexts and select_kube_context.
# Prevents AI from calling both in the same response without waiting for user input.
_CONTEXT_SELECT_MIN_DELAY: float = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(msg: str) -> list[TextContent]:
    """Wrap a string in the TextContent list that every handler must return."""
    return [TextContent(type="text", text=msg)]


def _normalize_path(path: str) -> str:
    """Expand ~ and resolve relative paths."""
    return str(Path(path).expanduser().resolve())


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

@app.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="select_kube_context",
            description=(
                "Select the Kubernetes context for all subsequent operations.\n"
                "MUST be called before using any other tool.\n"
                "Does NOT mutate global kubeconfig — context is held in memory only.\n"
                "IMPORTANT: Do NOT call this automatically.\n"
                "Always list contexts first and ask the user which context to use."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Name of the kubectl context to use",
                    }
                },
                "required": ["context"],
            },
        ),
        Tool(
            name="list_kube_contexts",
            description=(
                "List available kubectl contexts.\n"
                "Use this to see available contexts, then ALWAYS present the list\n"
                "to the user and ask them which context they want to use before\n"
                "calling select_kube_context.\n"
                "NEVER automatically select a context without user confirmation."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="flux_dryrun",
            description=(
                "Validate FluxCD manifests with kubectl dry-run (client + server).\n"
                "ALWAYS use this before committing Flux YAML files\n"
                "to prevent GitOps reconciliation failures.\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to YAML file or directory containing manifests (required)",
                    }
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="flux_check",
            description=(
                "Run 'flux check' to verify Flux installation and components health.\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="flux_status",
            description=(
                "Get Flux reconciliation status for all resources across namespaces.\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="kustomize_dryrun",
            description=(
                "Validate Kustomize overlay by building and running kubectl dry-run\n"
                "(client + server).\n"
                "ALWAYS use this before committing Kustomize overlay changes\n"
                "to prevent deployment failures.\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to directory containing kustomization.yaml"
                            " or path to kustomization.yaml file (required)"
                        ),
                    }
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="helm_dryrun",
            description=(
                "Validate Helm chart by rendering and running kubectl dry-run\n"
                "(client + server).\n"
                "ALWAYS use this before committing Helm chart changes\n"
                "to prevent deployment failures.\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "chart_path": {
                        "type": "string",
                        "description": "Path to Helm chart directory (required)",
                    },
                    "values_file": {
                        "type": "string",
                        "description": "Path to values file (optional)",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace for rendering (optional)",
                    },
                    "release_name": {
                        "type": "string",
                        "description": "Release name for helm template (default: 'release-name')",
                    },
                },
                "required": ["chart_path"],
            },
        ),
        Tool(
            name="kubeconform_validate",
            description=(
                "Validate Kubernetes manifests against JSON schemas offline\n"
                "using kubeconform. Catches invalid fields, type mismatches,\n"
                "and missing required fields without a live cluster.\n"
                "Does NOT require select_kube_context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to YAML file or directory containing manifests (required)",
                    },
                    "kubernetes_version": {
                        "type": "string",
                        "description": (
                            "Kubernetes version for schema lookup"
                            " (e.g. '1.29.0'). Default: 'master'"
                        ),
                    },
                    "strict": {
                        "type": "boolean",
                        "description": (
                            "Reject additional properties not in the schema"
                            " (default: false)"
                        ),
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="yaml_validate",
            description=(
                "Validate YAML syntax of Kubernetes manifest files.\n"
                "Catches syntax errors, duplicate keys, and tab indentation.\n"
                "Use this as a first-pass check before kubeconform or dry-run.\n"
                "Does NOT require select_kube_context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to YAML file or directory containing"
                            " YAML files (required)"
                        ),
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="argocd_app_list",
            description=(
                "List all ArgoCD applications with sync and health status.\n"
                "Uses --core mode (kubeconfig only, no ArgoCD server auth needed).\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": (
                            "Namespace where ArgoCD Application CRs live (optional)."
                            " Common values: 'argocd', 'argo-cd'"
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="argocd_app_get",
            description=(
                "Get detailed status of a single ArgoCD application including\n"
                "sync/health status, conditions, and resource statuses.\n"
                "Uses --core mode (kubeconfig only, no ArgoCD server auth needed).\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the ArgoCD Application (required)",
                    },
                    "namespace": {
                        "type": "string",
                        "description": (
                            "Namespace where the Application CR lives (optional)."
                            " Common values: 'argocd', 'argo-cd'"
                        ),
                    },
                },
                "required": ["app_name"],
            },
        ),
        Tool(
            name="argocd_app_diff",
            description=(
                "Show diff between live and desired state of an ArgoCD application.\n"
                "Returns unified diff output showing what would change on sync.\n"
                "Exit 0 = in sync, exit 1 = has diff, exit 2 = error.\n"
                "Uses --core mode (kubeconfig only, no ArgoCD server auth needed).\n"
                "Requires select_kube_context to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the ArgoCD Application (required)",
                    },
                    "namespace": {
                        "type": "string",
                        "description": (
                            "Namespace where the Application CR lives (optional)."
                            " Common values: 'argocd', 'argo-cd'"
                        ),
                    },
                },
                "required": ["app_name"],
            },
        ),
    ]


def _require_context() -> list[TextContent] | str:
    """Return the selected context string, or an error response if none is selected."""
    if _selected_context is None:
        return [TextContent(
            type="text",
            text=(
                "Error: No context selected. Call select_kube_context first."
                "\n\nUse list_kube_contexts to see available contexts."
            ),
        )]
    return _selected_context


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def _handle_select_context(arguments: dict[str, Any]) -> list[TextContent]:
    global _selected_context

    if _contexts_listed_at is None:
        return _text(
            "Error: You must call list_kube_contexts first and present the list "
            "to the user before selecting a context.\n"
            "This ensures the user explicitly chooses which cluster to target."
        )

    elapsed = time.monotonic() - _contexts_listed_at
    if elapsed < _CONTEXT_SELECT_MIN_DELAY:
        return _text(
            "Error: You must wait for the user to choose a context.\n"
            "list_kube_contexts was called less than 2 seconds ago — "
            "this means you called both tools in the same response.\n\n"
            "Present the context list to the user, STOP, and wait for "
            "their selection before calling select_kube_context."
        )

    ctx = arguments.get("context")
    if not ctx:
        return _text("Error: 'context' parameter is required")

    contexts, current = flux_lint.get_kubectl_contexts()
    if ctx not in contexts:
        lines = [f"Error: Context '{ctx}' not found.", "", "Available contexts:"]
        for c in contexts:
            marker = " (current global)" if c == current else ""
            lines.append(f"  - {c}{marker}")
        return _text("\n".join(lines))

    _selected_context = ctx
    logger.info("Context selected: %s", ctx)
    return _text(
        f"Context selected: {ctx}\n\n"
        "All subsequent operations will target this context "
        "via --context flag (no global kubeconfig mutation)."
    )


def _handle_list_contexts(arguments: dict[str, Any]) -> list[TextContent]:
    global _contexts_listed_at
    _contexts_listed_at = time.monotonic()

    contexts, current = flux_lint.get_kubectl_contexts()

    if not contexts:
        return _text("No kubectl contexts found. Is kubectl configured?")

    lines = ["Available Kubernetes Contexts:", ""]
    for ctx in contexts:
        marker = ""
        if ctx == _selected_context:
            marker = " <-- selected"
        elif ctx == current:
            marker = " (global current)"
        lines.append(f"  -> {ctx}{marker}")

    lines.append("")
    if _selected_context:
        lines.append(f"Selected context: {_selected_context}")
    else:
        lines.append(
            "No context selected."
            " Ask the user which context to use, then call select_kube_context."
        )

    return _text("\n".join(lines))


def _handle_flux_dryrun(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    path = arguments.get("path")
    if not path:
        return _text("Error: 'path' parameter is required")
    path = _normalize_path(path)

    results = flux_lint.validate_manifests(path, context=ctx)

    if not results:
        return _text(f"No YAML files found in: {path}")

    return _text(formatters.format_flux_results(results, ctx, path))


def _handle_flux_check(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    success, output = flux_lint.run_flux_check(context=ctx)

    status = "Flux Check: HEALTHY" if success else "Flux Check: UNHEALTHY"
    return _text(f"Context: {ctx}\n{status}\n\n{output}")


def _handle_flux_status(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    success, output = flux_lint.get_flux_status(context=ctx)

    if success:
        return _text(f"Context: {ctx}\nFlux Status:\n\n{output}")
    else:
        return _text(f"Context: {ctx}\nError getting Flux status:\n\n{output}")


def _handle_kustomize_dryrun(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    path = arguments.get("path")
    if not path:
        return _text("Error: 'path' parameter is required")
    path = _normalize_path(path)

    if not kustomize_lint.is_kustomization(path):
        return _text(
            f"Error: Path '{path}' is not a Kustomize overlay"
            " (missing kustomization.yaml)"
        )

    result = kustomize_lint.validate_kustomization(
        path=path, context=ctx,
    )

    return _text(formatters.format_kustomize_result(result, ctx, path))


def _handle_helm_dryrun(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    chart_path = arguments.get("chart_path")
    if not chart_path:
        return _text("Error: 'chart_path' parameter is required")
    chart_path = _normalize_path(chart_path)

    values_file = arguments.get("values_file")
    if values_file:
        values_file = _normalize_path(values_file)
    namespace = arguments.get("namespace")
    release_name = arguments.get("release_name", "release-name")

    if not helm_lint.is_helm_chart(chart_path):
        return _text(
            f"Error: Path '{chart_path}' is not a Helm chart (missing Chart.yaml)"
        )

    result = helm_lint.validate_helm_chart(
        chart_path=chart_path,
        values_file=values_file,
        context=ctx,
        namespace=namespace,
        release_name=release_name,
    )

    return _text(
        formatters.format_helm_result(result, ctx, chart_path, values_file, namespace)
    )


def _handle_kubeconform_validate(arguments: dict[str, Any]) -> list[TextContent]:
    path = arguments.get("path")
    if not path:
        return _text("Error: 'path' parameter is required")
    path = _normalize_path(path)

    kubernetes_version = arguments.get("kubernetes_version", "master")
    strict = arguments.get("strict", False)

    result = kubeconform_lint.validate_manifests(
        path=path,
        kubernetes_version=kubernetes_version,
        strict=strict,
    )

    if result.error:
        return _text(f"Error: {result.error}")

    return _text(
        formatters.format_kubeconform_result(result, path, kubernetes_version, strict)
    )


def _handle_yaml_validate(arguments: dict[str, Any]) -> list[TextContent]:
    path = arguments.get("path")
    if not path:
        return _text("Error: 'path' parameter is required")
    path = _normalize_path(path)

    result = yaml_lint.validate_yaml(path)

    return _text(formatters.format_yaml_result(result, path))


def _handle_argocd_app_list(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    namespace = arguments.get("namespace")
    result = argocd_lint.list_argocd_apps(context=ctx, namespace=namespace)

    if not result.success:
        return _text(f"Error listing ArgoCD apps: {result.error}")

    return _text(formatters.format_argocd_app_list_result(result, ctx, namespace))


def _handle_argocd_app_get(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    app_name = arguments.get("app_name")
    if not app_name:
        return _text("Error: 'app_name' parameter is required")

    namespace = arguments.get("namespace")
    result = argocd_lint.get_argocd_app(
        app_name=app_name, context=ctx, namespace=namespace,
    )

    if not result.success:
        return _text(f"Error getting ArgoCD app '{app_name}': {result.error}")

    return _text(formatters.format_argocd_app_get_result(result, ctx))


def _handle_argocd_app_diff(arguments: dict[str, Any]) -> list[TextContent]:
    ctx = _require_context()
    if isinstance(ctx, list):
        return ctx

    app_name = arguments.get("app_name")
    if not app_name:
        return _text("Error: 'app_name' parameter is required")

    namespace = arguments.get("namespace")
    result = argocd_lint.diff_argocd_app(
        app_name=app_name, context=ctx, namespace=namespace,
    )

    if not result.success:
        return _text(f"Error diffing ArgoCD app '{app_name}': {result.error}")

    return _text(formatters.format_argocd_app_diff_result(result, ctx, app_name))


# ---------------------------------------------------------------------------
# Dispatch table + call_tool
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Callable[[dict[str, Any]], list[TextContent]]] = {
    "select_kube_context": _handle_select_context,
    "list_kube_contexts": _handle_list_contexts,
    "flux_dryrun": _handle_flux_dryrun,
    "flux_check": _handle_flux_check,
    "flux_status": _handle_flux_status,
    "kustomize_dryrun": _handle_kustomize_dryrun,
    "helm_dryrun": _handle_helm_dryrun,
    "kubeconform_validate": _handle_kubeconform_validate,
    "yaml_validate": _handle_yaml_validate,
    "argocd_app_list": _handle_argocd_app_list,
    "argocd_app_get": _handle_argocd_app_get,
    "argocd_app_diff": _handle_argocd_app_diff,
}


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(
    name: str, arguments: dict[str, Any] | None = None
) -> Sequence[TextContent]:
    """Handle tool calls."""
    if arguments is None:
        arguments = {}

    handler = _HANDLERS.get(name)
    if handler is None:
        return _text(f"Unknown tool: {name}")

    return await asyncio.to_thread(handler, arguments)


async def main() -> None:  # pragma: no cover
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
