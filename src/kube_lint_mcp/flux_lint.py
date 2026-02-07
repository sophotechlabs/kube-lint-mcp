"""FluxCD and Kubernetes manifest validation utilities."""

import logging
import os
import subprocess
from pathlib import Path
from dataclasses import dataclass

from kube_lint_mcp.dryrun import build_ctx_args, kubectl_dry_run


logger = logging.getLogger(__name__)

FLUX_TIMEOUT = int(os.getenv("KUBE_LINT_FLUX_TIMEOUT", "60"))


@dataclass
class ValidationResult:
    """Result of a dry-run validation."""

    file: str
    client_passed: bool
    server_passed: bool
    client_error: str | None = None
    server_error: str | None = None
    warnings: list[str] | None = None


def get_kubectl_contexts() -> tuple[list[str], str | None]:
    """Get list of available kubectl contexts and current context.

    Returns:
        Tuple of (list of context names, current context name or None)
    """
    try:
        # Get all contexts
        result = subprocess.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        contexts = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]

        # Get current context
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        current = result.stdout.strip() if result.returncode == 0 else None

        return contexts, current
    except subprocess.TimeoutExpired:
        return [], None
    except FileNotFoundError:
        return [], None


def context_exists(context: str) -> bool:
    """Check if a kubectl context exists.

    Args:
        context: Name of the context to check

    Returns:
        True if context exists
    """
    contexts, _ = get_kubectl_contexts()
    return context in contexts


def find_yaml_files(path: str) -> list[str]:
    """Find all YAML files in a path.

    Args:
        path: File path or directory path

    Returns:
        List of YAML file paths
    """
    p = Path(path)
    if p.is_file():
        if p.suffix in (".yaml", ".yml"):
            return [str(p)]
        return []
    elif p.is_dir():
        files = []
        for ext in ("*.yaml", "*.yml"):
            files.extend([str(f) for f in p.rglob(ext)])
        return sorted(files)
    return []


def validate_manifest(file_path: str, context: str | None = None) -> ValidationResult:
    """Run dry-run validation on a manifest file.

    Args:
        file_path: Path to the YAML manifest
        context: Optional kubectl context to use via --context flag (no global mutation)

    Returns:
        ValidationResult with pass/fail status and any errors
    """
    logger.debug("Validating manifest: %s", file_path)
    dr = kubectl_dry_run(file_path, context=context)
    result = ValidationResult(
        file=file_path,
        client_passed=dr.client_passed,
        server_passed=dr.server_passed,
        client_error=dr.client_error,
        server_error=dr.server_error,
        warnings=dr.warnings,
    )
    if not result.client_passed:
        logger.warning("Client dry-run failed for %s: %s", file_path, result.client_error)
    elif not result.server_passed:
        logger.warning("Server dry-run failed for %s: %s", file_path, result.server_error)
    else:
        logger.debug("Manifest validated successfully: %s", file_path)
    return result


def validate_manifests(path: str, context: str | None = None) -> list[ValidationResult]:
    """Validate all manifests in a path.

    Args:
        path: File or directory path
        context: Optional kubectl context to use via --context flag (no global mutation)

    Returns:
        List of ValidationResult for each file
    """
    files = find_yaml_files(path)
    if not files:
        return []

    results = []
    for file in files:
        result = validate_manifest(file, context=context)
        results.append(result)
    return results


def run_flux_check(context: str | None = None) -> tuple[bool, str]:
    """Run 'flux check' command.

    Args:
        context: Optional kubectl context to use via --context flag (no global mutation)

    Returns:
        Tuple of (success, output)
    """
    ctx_args = build_ctx_args(context)
    logger.debug("Running flux check with context: %s", context)
    try:
        result = subprocess.run(
            ["flux", *ctx_args, "check"],
            capture_output=True,
            text=True,
            timeout=FLUX_TIMEOUT,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        logger.error("flux check timed out after %ds", FLUX_TIMEOUT)
        return False, "Timeout running flux check"
    except FileNotFoundError:
        logger.error("flux CLI not found on PATH")
        return False, "flux CLI not found"


def get_flux_status(context: str | None = None) -> tuple[bool, str]:
    """Get Flux reconciliation status.

    Args:
        context: Optional kubectl context to use via --context flag (no global mutation)

    Returns:
        Tuple of (success, output)
    """
    ctx_args = build_ctx_args(context)
    logger.debug("Getting flux status with context: %s", context)
    try:
        result = subprocess.run(
            ["flux", *ctx_args, "get", "all", "-A"],
            capture_output=True,
            text=True,
            timeout=FLUX_TIMEOUT,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        logger.error("flux get all timed out after %ds", FLUX_TIMEOUT)
        return False, "Timeout getting flux status"
    except FileNotFoundError:
        logger.error("flux CLI not found on PATH")
        return False, "flux CLI not found"
