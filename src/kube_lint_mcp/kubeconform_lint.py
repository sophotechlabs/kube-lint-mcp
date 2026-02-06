"""Offline schema validation using kubeconform."""

import json
import subprocess
from dataclasses import dataclass, field

KUBECONFORM_TIMEOUT = 120


@dataclass
class KubeconformResourceResult:
    """Result for a single validated resource."""

    filename: str
    kind: str
    name: str
    version: str
    status: str
    msg: str = ""


@dataclass
class KubeconformResult:
    """Overall result of kubeconform validation."""

    path: str
    passed: bool
    resources: list[KubeconformResourceResult] = field(default_factory=list)
    valid: int = 0
    invalid: int = 0
    errors: int = 0
    skipped: int = 0
    error: str | None = None


def _parse_output(stdout: str) -> list[KubeconformResourceResult]:
    """Parse kubeconform JSON output into resource results.

    Handles both wrapped JSON ({"resources": [...]}) and JSONL formats.
    """
    stdout = stdout.strip()
    if not stdout:
        return []

    # Try wrapped JSON first
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and "resources" in data:
            return [
                KubeconformResourceResult(
                    filename=r.get("filename", ""),
                    kind=r.get("kind", ""),
                    name=r.get("name", ""),
                    version=r.get("version", ""),
                    status=r.get("status", ""),
                    msg=r.get("msg", ""),
                )
                for r in data["resources"]
            ]
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to JSONL (one JSON object per line)
    resources = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if isinstance(r, dict) and "filename" in r:
                resources.append(
                    KubeconformResourceResult(
                        filename=r.get("filename", ""),
                        kind=r.get("kind", ""),
                        name=r.get("name", ""),
                        version=r.get("version", ""),
                        status=r.get("status", ""),
                        msg=r.get("msg", ""),
                    )
                )
        except (json.JSONDecodeError, TypeError):
            continue

    return resources


def validate_manifests(
    path: str,
    kubernetes_version: str = "master",
    strict: bool = False,
) -> KubeconformResult:
    """Run kubeconform schema validation on manifests.

    Args:
        path: Path to YAML file or directory.
        kubernetes_version: Kubernetes version for schema lookup (default: "master").
        strict: Reject additional properties not in the schema.

    Returns:
        KubeconformResult with per-resource details and counts.
    """
    cmd = [
        "kubeconform",
        "-output", "json",
        "-summary",
        "-ignore-missing-schemas",
    ]

    if kubernetes_version != "master":
        cmd.extend(["-kubernetes-version", kubernetes_version])

    if strict:
        cmd.append("-strict")

    cmd.append(path)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=KUBECONFORM_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return KubeconformResult(
            path=path,
            passed=False,
            error="Timeout during kubeconform validation",
        )
    except FileNotFoundError:
        return KubeconformResult(
            path=path,
            passed=False,
            error="kubeconform not found. Install: https://github.com/yannh/kubeconform",
        )

    resources = _parse_output(proc.stdout)

    valid = sum(1 for r in resources if r.status == "statusValid")
    invalid = sum(1 for r in resources if r.status == "statusInvalid")
    errors = sum(1 for r in resources if r.status == "statusError")
    skipped = sum(1 for r in resources if r.status == "statusSkipped")

    passed = invalid == 0 and errors == 0

    return KubeconformResult(
        path=path,
        passed=passed,
        resources=resources,
        valid=valid,
        invalid=invalid,
        errors=errors,
        skipped=skipped,
    )
