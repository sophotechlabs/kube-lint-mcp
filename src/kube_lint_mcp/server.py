"""MCP server for Kubernetes manifest validation."""

import asyncio
import sys
from typing import Any, Sequence

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:  # pragma: no cover
    print(
        "Error: MCP SDK not installed. Install with: pip install mcp", file=sys.stderr
    )
    sys.exit(1)

from kube_lint_mcp import flux_lint
from kube_lint_mcp import helm_lint

# Create MCP server instance
app = Server("kube-lint-mcp")

# In-memory context selection — no global kubeconfig mutation
_selected_context: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(msg: str) -> list[TextContent]:
    """Wrap a string in the TextContent list that every handler must return."""
    return [TextContent(type="text", text=msg)]


def _format_step(
    name: str,
    passed: bool,
    error: str | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    """Return output lines for a single validation step."""
    if passed:
        if warnings:
            lines = [f"{name}: PASS (with warnings)"]
            for w in warnings:
                lines.append(f"  Warning: {w}")
        else:
            lines = [f"{name}: PASS"]
    else:
        lines = [f"{name}: FAIL"]
        if error:
            lines.append(f"  Error: {error}")
    return lines


def _format_summary(passed: int, failed: int) -> list[str]:
    """Return the summary footer lines used by dryrun handlers."""
    lines = [
        "=" * 50,
        f"Summary: {passed} passed, {failed} failed",
        "",
    ]
    if failed > 0:
        lines.append("DO NOT COMMIT - Fix errors first!")
    else:
        lines.append("All validations passed. Safe to commit.")
    return lines


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="select_kube_context",
            description=(
                "Select the Kubernetes context for all subsequent operations."
                " MUST be called before using any other tool."
                " Does NOT mutate global kubeconfig — context is held in memory only."
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
                "List available kubectl contexts."
                " Use this to see available contexts, then call select_kube_context to choose one."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="flux_dryrun",
            description=(
                "Validate FluxCD manifests with kubectl dry-run (client + server)."
                " ALWAYS use this before committing Flux YAML files"
                " to prevent GitOps reconciliation failures."
                " Requires select_kube_context to be called first."
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
                "Run 'flux check' to verify Flux installation and components health."
                " Requires select_kube_context to be called first."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="flux_status",
            description=(
                "Get Flux reconciliation status for all resources across namespaces."
                " Requires select_kube_context to be called first."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="helm_dryrun",
            description=(
                "Validate Helm chart by rendering and running kubectl dry-run (client + server)."
                " ALWAYS use this before committing Helm chart changes"
                " to prevent deployment failures."
                " Requires select_kube_context to be called first."
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
    ]


def _require_context() -> TextContent | None:
    """Return an error TextContent if no context is selected, else None."""
    if _selected_context is None:
        return TextContent(
            type="text",
            text=(
                "Error: No context selected. Call select_kube_context first."
                "\n\nUse list_kube_contexts to see available contexts."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def _handle_select_context(arguments: dict[str, Any]) -> list[TextContent]:
    global _selected_context

    ctx = arguments.get("context")
    if not ctx:
        return _text("Error: 'context' parameter is required")

    if not flux_lint.context_exists(ctx):
        contexts, current = flux_lint.get_kubectl_contexts()
        lines = [f"Error: Context '{ctx}' not found.", "", "Available contexts:"]
        for c in contexts:
            marker = " (current global)" if c == current else ""
            lines.append(f"  - {c}{marker}")
        return _text("\n".join(lines))

    _selected_context = ctx
    return _text(
        f"Context selected: {ctx}\n\n"
        "All subsequent operations will target this context "
        "via --context flag (no global kubeconfig mutation)."
    )


def _handle_list_contexts(arguments: dict[str, Any]) -> list[TextContent]:
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
        lines.append("No context selected. Use select_kube_context to choose one.")

    return _text("\n".join(lines))


def _handle_flux_dryrun(arguments: dict[str, Any]) -> list[TextContent]:
    err = _require_context()
    if err:
        return [err]

    path = arguments.get("path")
    if not path:
        return _text("Error: 'path' parameter is required")

    results = flux_lint.validate_manifests(path, context=_selected_context)

    if not results:
        return _text(f"No YAML files found in: {path}")

    lines = [
        "FluxCD Dry-Run Validation",
        f"Context: {_selected_context}",
        f"Path: {path}",
        "=" * 50,
        "",
    ]

    passed = 0
    failed = 0

    for r in results:
        lines.append(f"File: {r.file}")

        if r.client_passed:
            lines.append("  Client dry-run: PASS")
        else:
            step = _format_step("Client dry-run", False, r.client_error)
            lines.extend(["  " + ln for ln in step])
            failed += 1
            lines.append("")
            continue

        if r.server_passed:
            step = _format_step("Server dry-run", True, warnings=r.warnings)
            lines.extend(["  " + ln for ln in step])
            passed += 1
        else:
            step = _format_step("Server dry-run", False, r.server_error)
            lines.extend(["  " + ln for ln in step])
            failed += 1

        lines.append("")

    lines.extend(_format_summary(passed, failed))

    return _text("\n".join(lines))


def _handle_flux_check(arguments: dict[str, Any]) -> list[TextContent]:
    err = _require_context()
    if err:
        return [err]

    success, output = flux_lint.run_flux_check(context=_selected_context)

    status = "Flux Check: HEALTHY" if success else "Flux Check: UNHEALTHY"
    return _text(f"Context: {_selected_context}\n{status}\n\n{output}")


def _handle_flux_status(arguments: dict[str, Any]) -> list[TextContent]:
    err = _require_context()
    if err:
        return [err]

    success, output = flux_lint.get_flux_status(context=_selected_context)

    if success:
        return _text(f"Context: {_selected_context}\nFlux Status:\n\n{output}")
    else:
        return _text(f"Context: {_selected_context}\nError getting Flux status:\n\n{output}")


def _handle_helm_dryrun(arguments: dict[str, Any]) -> list[TextContent]:
    err = _require_context()
    if err:
        return [err]

    chart_path = arguments.get("chart_path")
    if not chart_path:
        return _text("Error: 'chart_path' parameter is required")

    values_file = arguments.get("values_file")
    namespace = arguments.get("namespace")
    release_name = arguments.get("release_name", "release-name")

    if not helm_lint.is_helm_chart(chart_path):
        return _text(
            f"Error: Path '{chart_path}' is not a Helm chart (missing Chart.yaml)"
        )

    result = helm_lint.validate_helm_chart(
        chart_path=chart_path,
        values_file=values_file,
        context=_selected_context,
        namespace=namespace,
        release_name=release_name,
    )

    lines = [
        "Helm Chart Dry-Run Validation",
        f"Context: {_selected_context}",
        f"Chart: {chart_path}",
    ]
    if values_file:
        lines.append(f"Values: {values_file}")
    if namespace:
        lines.append(f"Namespace: {namespace}")
    lines.extend(["=" * 50, ""])

    passed = 0
    failed = 0

    lines.extend(_format_step("Helm lint", result.lint_passed, result.lint_error))
    if result.lint_passed:
        passed += 1
    else:
        failed += 1
    lines.append("")

    if result.render_passed:
        lines.append(f"Helm template: PASS ({result.resource_count} resources)")
        passed += 1
    else:
        lines.extend(_format_step("Helm template", False, result.render_error))
        failed += 1
    lines.append("")

    lines.extend(
        _format_step("Client dry-run", result.client_passed, result.client_error)
    )
    if result.client_passed:
        passed += 1
    else:
        failed += 1
    lines.append("")

    lines.extend(
        _format_step(
            "Server dry-run", result.server_passed,
            result.server_error, result.warnings,
        )
    )
    if result.server_passed:
        passed += 1
    else:
        failed += 1

    lines.append("")

    lines.append("=" * 50)
    if failed > 0:
        lines.append("DO NOT COMMIT - Fix errors first!")
    else:
        lines.append("All validations passed. Safe to commit.")

    return _text("\n".join(lines))


# ---------------------------------------------------------------------------
# Dispatch table + call_tool
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "select_kube_context": _handle_select_context,
    "list_kube_contexts": _handle_list_contexts,
    "flux_dryrun": _handle_flux_dryrun,
    "flux_check": _handle_flux_check,
    "flux_status": _handle_flux_status,
    "helm_dryrun": _handle_helm_dryrun,
}


@app.call_tool()
async def call_tool(
    name: str, arguments: dict[str, Any] | None = None
) -> Sequence[TextContent]:
    """Handle tool calls."""
    if arguments is None:
        arguments = {}

    handler = _HANDLERS.get(name)
    if handler is None:
        return _text(f"Unknown tool: {name}")

    return handler(arguments)


async def main():  # pragma: no cover
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
