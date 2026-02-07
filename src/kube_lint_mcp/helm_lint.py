"""Helm chart validation utilities."""

import logging
import os
import subprocess
import yaml
from pathlib import Path
from dataclasses import dataclass

from kube_lint_mcp.dryrun import kubectl_dry_run


logger = logging.getLogger(__name__)

HELM_TIMEOUT = int(os.getenv("KUBE_LINT_HELM_TIMEOUT", "60"))


@dataclass
class HelmValidationResult:
    """Result of Helm chart validation."""

    chart_path: str
    lint_passed: bool
    render_passed: bool
    client_passed: bool
    server_passed: bool
    lint_error: str | None = None
    render_error: str | None = None
    client_error: str | None = None
    server_error: str | None = None
    warnings: list[str] | None = None
    resource_count: int = 0


def is_helm_chart(path: str) -> bool:
    """Check if path is a Helm chart.

    Args:
        path: Path to check

    Returns:
        True if path contains Chart.yaml or chart.yaml
    """
    p = Path(path)
    if p.is_file():
        # Check if parent directory is a chart
        return (p.parent / "Chart.yaml").exists() or (p.parent / "chart.yaml").exists()
    elif p.is_dir():
        return (p / "Chart.yaml").exists() or (p / "chart.yaml").exists()
    return False


def validate_helm_chart(
    chart_path: str,
    values_file: str | None = None,
    context: str | None = None,
    namespace: str | None = None,
    release_name: str = "release-name",
) -> HelmValidationResult:
    """Validate Helm chart by linting, rendering, and validating rendered manifests.

    Args:
        chart_path: Path to Helm chart directory
        values_file: Optional path to values file
        context: Optional kubectl context to use via --context flag (no global mutation)
        namespace: Optional namespace for rendering
        release_name: Release name for helm template (default: "release-name")

    Returns:
        HelmValidationResult with validation status
    """
    if not is_helm_chart(chart_path):
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=False,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error="Path is not a Helm chart (missing Chart.yaml)",
        )

    # Step 1: Run helm lint (no context needed, local-only)
    lint_cmd = ["helm", "lint", chart_path]
    if values_file:
        lint_cmd.extend(["-f", values_file])

    logger.debug("Running helm lint: %s", " ".join(lint_cmd))

    try:
        lint_result = subprocess.run(
            lint_cmd, capture_output=True, text=True, timeout=HELM_TIMEOUT
        )
    except FileNotFoundError:
        logger.error("helm not found on PATH")
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=False,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error="helm not found",
        )
    except subprocess.TimeoutExpired:
        logger.error("helm lint timed out after %ds", HELM_TIMEOUT)
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=False,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error="Timeout during validation",
        )

    lint_passed = lint_result.returncode == 0
    lint_error = lint_result.stderr.strip() if not lint_passed else None

    # Step 2: Render chart with helm template (no context needed, local-only)
    render_cmd = ["helm", "template", release_name, chart_path]
    if values_file:
        render_cmd.extend(["-f", values_file])
    if namespace:
        render_cmd.extend(["--namespace", namespace])

    logger.debug("Running helm template: %s", " ".join(render_cmd))

    try:
        render_result = subprocess.run(
            render_cmd, capture_output=True, text=True, timeout=HELM_TIMEOUT
        )
    except FileNotFoundError:
        logger.error("helm not found on PATH")
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=lint_passed,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error=lint_error,
            render_error="helm not found",
        )
    except subprocess.TimeoutExpired:
        logger.error("helm template timed out after %ds", HELM_TIMEOUT)
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=lint_passed,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error=lint_error,
            render_error="Timeout during validation",
        )

    render_passed = render_result.returncode == 0
    render_error = render_result.stderr.strip() if not render_passed else None

    if not render_passed:
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=lint_passed,
            render_passed=False,
            client_passed=False,
            server_passed=False,
            lint_error=lint_error,
            render_error=render_error,
        )

    # Count resources in rendered output
    try:
        rendered_manifests = list(yaml.safe_load_all(render_result.stdout))
        resource_count = len([m for m in rendered_manifests if m])
    except yaml.YAMLError as e:
        return HelmValidationResult(
            chart_path=chart_path,
            lint_passed=lint_passed,
            render_passed=True,
            client_passed=False,
            server_passed=False,
            lint_error=lint_error,
            render_error=f"Failed to parse rendered YAML: {e}",
        )

    # Step 3: Validate rendered manifests with kubectl via stdin
    dr = kubectl_dry_run(context=context, stdin_data=render_result.stdout)
    return HelmValidationResult(
        chart_path=chart_path,
        lint_passed=lint_passed,
        render_passed=render_passed,
        client_passed=dr.client_passed,
        server_passed=dr.server_passed,
        lint_error=lint_error,
        client_error=dr.client_error,
        server_error=dr.server_error,
        warnings=dr.warnings,
        resource_count=resource_count,
    )
