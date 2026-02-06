"""Shared kubectl utilities for dry-run validation."""

import subprocess
from dataclasses import dataclass


KUBECTL_TIMEOUT = 60


@dataclass
class DryRunResult:
    """Result of a client + server kubectl dry-run pair."""

    client_passed: bool
    server_passed: bool
    client_error: str | None = None
    server_error: str | None = None
    warnings: list[str] | None = None


def build_ctx_args(context: str | None) -> list[str]:
    """Build --context args for kubectl/flux commands."""
    return ["--context", context] if context else []


def parse_deprecation_warnings(output: str) -> list[str]:
    """Extract deprecation warning lines from kubectl output."""
    warnings = []
    for line in output.split("\n"):
        if "deprecated" in line.lower():
            warnings.append(line.strip())
    return warnings


def kubectl_dry_run(
    file_path: str | None = None,
    context: str | None = None,
    timeout: int = KUBECTL_TIMEOUT,
    stdin_data: str | None = None,
) -> DryRunResult:
    """Run client + server kubectl dry-run on a manifest file or stdin data.

    Args:
        file_path: Path to the YAML manifest file (used when stdin_data is None)
        context: Optional kubectl context (passed via --context flag)
        timeout: Timeout in seconds for each subprocess call
        stdin_data: Optional YAML string to pipe via stdin instead of reading a file

    Returns:
        DryRunResult with client/server pass/fail and any deprecation warnings
    """
    ctx_args = build_ctx_args(context)
    source_args = ["-f", "-"] if stdin_data is not None else ["-f", file_path]

    try:
        # Client dry-run
        client_result = subprocess.run(
            ["kubectl", *ctx_args, "apply", "--dry-run=client", *source_args],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
        )
        client_passed = client_result.returncode == 0
        client_error = client_result.stderr.strip() if not client_passed else None

        if not client_passed:
            return DryRunResult(
                client_passed=False,
                server_passed=False,
                client_error=client_error,
            )

        # Server dry-run
        server_result = subprocess.run(
            ["kubectl", *ctx_args, "apply", "--dry-run=server", *source_args],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
        )
        server_passed = server_result.returncode == 0
        server_error = server_result.stderr.strip() if not server_passed else None

        output = server_result.stdout + server_result.stderr
        warnings = parse_deprecation_warnings(output)

        return DryRunResult(
            client_passed=True,
            server_passed=server_passed,
            server_error=server_error,
            warnings=warnings if warnings else None,
        )

    except subprocess.TimeoutExpired:
        return DryRunResult(
            client_passed=False,
            server_passed=False,
            client_error="Timeout during validation",
        )
    except FileNotFoundError:
        return DryRunResult(
            client_passed=False,
            server_passed=False,
            client_error="kubectl not found",
        )
