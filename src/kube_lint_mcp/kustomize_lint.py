"""Kustomize overlay validation utilities."""

import subprocess
import os
import tempfile
import yaml
from pathlib import Path
from dataclasses import dataclass

from kube_lint_mcp.dryrun import kubectl_dry_run


KUSTOMIZATION_FILENAMES = ("kustomization.yaml", "kustomization.yml", "Kustomization")


@dataclass
class KustomizeValidationResult:
    """Result of Kustomize overlay validation."""

    path: str
    build_passed: bool
    client_passed: bool
    server_passed: bool
    build_error: str | None = None
    client_error: str | None = None
    server_error: str | None = None
    warnings: list[str] | None = None
    resource_count: int = 0


def is_kustomization(path: str) -> bool:
    """Check if path contains a kustomization.

    Args:
        path: Path to check

    Returns:
        True if path contains a kustomization file
    """
    p = Path(path)
    if p.is_file():
        return p.name in KUSTOMIZATION_FILENAMES
    elif p.is_dir():
        return any((p / name).exists() for name in KUSTOMIZATION_FILENAMES)
    return False


def validate_kustomization(
    path: str,
    context: str | None = None,
) -> KustomizeValidationResult:
    """Validate a Kustomize overlay by building and dry-running rendered manifests.

    Args:
        path: Path to directory containing kustomization.yaml
        context: Optional kubectl context to use via --context flag (no global mutation)

    Returns:
        KustomizeValidationResult with validation status
    """
    # Resolve to directory
    p = Path(path)
    kustomize_dir = str(p.parent) if p.is_file() else str(p)

    try:
        # Step 1: Build with kubectl kustomize
        build_result = subprocess.run(
            ["kubectl", "kustomize", kustomize_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        build_passed = build_result.returncode == 0
        build_error = build_result.stderr.strip() if not build_passed else None

        if not build_passed:
            return KustomizeValidationResult(
                path=path,
                build_passed=False,
                client_passed=False,
                server_passed=False,
                build_error=build_error,
            )

        # Count resources in rendered output
        try:
            rendered_manifests = list(yaml.safe_load_all(build_result.stdout))
            resource_count = len([m for m in rendered_manifests if m])
        except yaml.YAMLError as e:
            return KustomizeValidationResult(
                path=path,
                build_passed=True,
                client_passed=False,
                server_passed=False,
                build_error=f"Failed to parse rendered YAML: {e}",
            )

        # Step 2: Validate rendered manifests with kubectl dry-run
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(build_result.stdout)
            temp_file = f.name

        try:
            dr = kubectl_dry_run(temp_file, context=context)
            return KustomizeValidationResult(
                path=path,
                build_passed=True,
                client_passed=dr.client_passed,
                server_passed=dr.server_passed,
                client_error=dr.client_error,
                server_error=dr.server_error,
                warnings=dr.warnings,
                resource_count=resource_count,
            )
        finally:
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    except subprocess.TimeoutExpired:
        return KustomizeValidationResult(
            path=path,
            build_passed=False,
            client_passed=False,
            server_passed=False,
            build_error="Timeout during validation",
        )
    except FileNotFoundError:
        return KustomizeValidationResult(
            path=path,
            build_passed=False,
            client_passed=False,
            server_passed=False,
            build_error="kubectl not found",
        )
