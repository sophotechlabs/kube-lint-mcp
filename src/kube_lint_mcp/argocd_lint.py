"""ArgoCD application validation utilities."""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ARGOCD_TIMEOUT = int(os.getenv("KUBE_LINT_ARGOCD_TIMEOUT", "60"))


@dataclass
class ArgoAppSummary:
    """Summary of a single ArgoCD Application."""

    name: str
    namespace: str
    project: str
    sync_status: str
    health_status: str
    repo_url: str
    path: str
    target_revision: str


@dataclass
class ArgoAppListResult:
    """Result of listing ArgoCD applications."""

    success: bool
    apps: list[ArgoAppSummary] = field(default_factory=list)
    error: str | None = None


@dataclass
class ArgoAppGetResult:
    """Result of getting detailed ArgoCD application status."""

    success: bool
    name: str = ""
    namespace: str = ""
    project: str = ""
    sync_status: str = ""
    health_status: str = ""
    sync_message: str = ""
    health_message: str = ""
    repo_url: str = ""
    path: str = ""
    target_revision: str = ""
    resources: list[dict[str, str]] | None = None
    conditions: list[str] | None = None
    error: str | None = None


@dataclass
class ArgoAppDiffResult:
    """Result of ArgoCD app diff (live vs desired state)."""

    success: bool
    in_sync: bool = False
    diff_output: str = ""
    error: str | None = None


def _detect_argocd_namespace(context: str) -> str | None:
    """Auto-detect the namespace where ArgoCD is installed.

    Looks for the argocd-cm configmap across all namespaces.

    Args:
        context: kubectl context to use

    Returns:
        Namespace name if found, None otherwise
    """
    cmd = [
        "kubectl", "get", "configmap", "argocd-cm",
        "--all-namespaces",
        "--context", context,
        "-o", "jsonpath={.items[0].metadata.namespace}",
    ]
    logger.debug("Auto-detecting ArgoCD namespace: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            ns = result.stdout.strip()
            logger.debug("Auto-detected ArgoCD namespace: %s", ns)
            return ns
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    logger.debug("Could not auto-detect ArgoCD namespace")
    return None


def _build_argocd_args(context: str, namespace: str | None = None) -> list[str]:
    """Build common ArgoCD CLI args.

    Args:
        context: kubectl context to use (passed via --kube-context flag)
        namespace: Optional namespace filter

    Returns:
        List of CLI arguments: --core --kube-context CTX [-n NS]
    """
    args = ["--core", "--kube-context", context]
    if namespace:
        args.extend(["-n", namespace])
    return args


def _extract_source(spec: dict[str, object]) -> tuple[str, str, str]:
    """Extract repo_url, path, target_revision from spec.source or spec.sources[0]."""
    source = spec.get("source", {})
    if not source and "sources" in spec:
        sources = spec.get("sources", [])
        if isinstance(sources, list) and sources:
            source = sources[0]
    if not isinstance(source, dict):
        source = {}
    repo_url = str(source.get("repoURL", ""))
    path = str(source.get("path", ""))
    target_revision = str(source.get("targetRevision", ""))
    return repo_url, path, target_revision


def list_argocd_apps(
    context: str,
    namespace: str | None = None,
) -> ArgoAppListResult:
    """List all ArgoCD applications with sync/health status.

    Args:
        context: kubectl context to use (passed via --kube-context flag)
        namespace: Optional namespace where Application CRs live

    Returns:
        ArgoAppListResult with list of app summaries
    """
    if not namespace:
        namespace = _detect_argocd_namespace(context)
        if not namespace:
            return ArgoAppListResult(
                success=False,
                error="Could not auto-detect ArgoCD namespace (argocd-cm configmap not found in any namespace). "
                "Specify the namespace parameter explicitly.",
            )
    base_args = _build_argocd_args(context, namespace)
    cmd = ["argocd", "app", "list", *base_args, "-o", "json"]

    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ARGOCD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("argocd app list timed out after %ds", ARGOCD_TIMEOUT)
        return ArgoAppListResult(success=False, error="Timeout running argocd app list")
    except FileNotFoundError:
        logger.error("argocd CLI not found on PATH")
        return ArgoAppListResult(success=False, error="argocd CLI not found")

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        logger.warning("argocd app list failed: %s", error)
        return ArgoAppListResult(success=False, error=error)

    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse argocd output: %s", exc)
        return ArgoAppListResult(
            success=False,
            error=f"Failed to parse argocd output: {exc}",
        )

    if not isinstance(items, list):
        items = []

    apps: list[ArgoAppSummary] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        status = item.get("status", {})

        repo_url, path, target_revision = _extract_source(spec)

        sync = status.get("sync", {})
        health = status.get("health", {})

        apps.append(ArgoAppSummary(
            name=str(metadata.get("name", "")),
            namespace=str(metadata.get("namespace", "")),
            project=str(spec.get("project", "")),
            sync_status=str(sync.get("status", "Unknown")),
            health_status=str(health.get("status", "Unknown")),
            repo_url=repo_url,
            path=path,
            target_revision=target_revision,
        ))

    return ArgoAppListResult(success=True, apps=apps)


def get_argocd_app(
    app_name: str,
    context: str,
    namespace: str | None = None,
) -> ArgoAppGetResult:
    """Get detailed status of a single ArgoCD application.

    Args:
        app_name: Name of the ArgoCD Application
        context: kubectl context to use (passed via --kube-context flag)
        namespace: Optional namespace where the Application CR lives

    Returns:
        ArgoAppGetResult with detailed app status
    """
    if not namespace:
        namespace = _detect_argocd_namespace(context)
        if not namespace:
            return ArgoAppGetResult(
                success=False,
                error="Could not auto-detect ArgoCD namespace (argocd-cm configmap not found in any namespace). "
                "Specify the namespace parameter explicitly.",
            )
    base_args = _build_argocd_args(context, namespace)
    cmd = ["argocd", "app", "get", app_name, *base_args, "-o", "json"]

    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ARGOCD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("argocd app get timed out after %ds", ARGOCD_TIMEOUT)
        return ArgoAppGetResult(success=False, error="Timeout running argocd app get")
    except FileNotFoundError:
        logger.error("argocd CLI not found on PATH")
        return ArgoAppGetResult(success=False, error="argocd CLI not found")

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        logger.warning("argocd app get failed: %s", error)
        return ArgoAppGetResult(success=False, error=error)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse argocd output: %s", exc)
        return ArgoAppGetResult(
            success=False,
            error=f"Failed to parse argocd output: {exc}",
        )

    if not isinstance(data, dict):
        return ArgoAppGetResult(success=False, error="Unexpected argocd output format")

    metadata = data.get("metadata", {})
    spec = data.get("spec", {})
    status = data.get("status", {})

    repo_url, path, target_revision = _extract_source(spec)

    sync = status.get("sync", {})
    health = status.get("health", {})

    # Extract resource statuses
    resources: list[dict[str, str]] | None = None
    raw_resources = status.get("resources")
    if isinstance(raw_resources, list) and raw_resources:
        resources = []
        for r in raw_resources:
            if not isinstance(r, dict):
                continue
            r_health = r.get("health", {})
            resources.append({
                "kind": str(r.get("kind", "")),
                "namespace": str(r.get("namespace", "")),
                "name": str(r.get("name", "")),
                "status": str(r.get("status", "")),
                "health": str(r_health.get("status", "")) if isinstance(r_health, dict) else "",
            })

    # Extract conditions
    conditions: list[str] | None = None
    raw_conditions = status.get("conditions")
    if isinstance(raw_conditions, list) and raw_conditions:
        conditions = []
        for c in raw_conditions:
            if isinstance(c, dict):
                ctype = c.get("type", "")
                cmsg = c.get("message", "")
                conditions.append(f"{ctype}: {cmsg}" if cmsg else str(ctype))

    return ArgoAppGetResult(
        success=True,
        name=str(metadata.get("name", "")),
        namespace=str(metadata.get("namespace", "")),
        project=str(spec.get("project", "")),
        sync_status=str(sync.get("status", "Unknown")),
        health_status=str(health.get("status", "Unknown")),
        sync_message=str(sync.get("revision", "")),
        health_message=str(health.get("message", "")),
        repo_url=repo_url,
        path=path,
        target_revision=target_revision,
        resources=resources,
        conditions=conditions,
    )


def diff_argocd_app(
    app_name: str,
    context: str,
    namespace: str | None = None,
) -> ArgoAppDiffResult:
    """Show diff between live and desired state of an ArgoCD application.

    Exit codes:
        0 = in sync (no diff)
        1 = has diff (diff output on stdout)
        2 = error

    Args:
        app_name: Name of the ArgoCD Application
        context: kubectl context to use (passed via --kube-context flag)
        namespace: Optional namespace where the Application CR lives

    Returns:
        ArgoAppDiffResult with sync status and diff output
    """
    if not namespace:
        namespace = _detect_argocd_namespace(context)
        if not namespace:
            return ArgoAppDiffResult(
                success=False,
                error="Could not auto-detect ArgoCD namespace (argocd-cm configmap not found in any namespace). "
                "Specify the namespace parameter explicitly.",
            )
    base_args = _build_argocd_args(context, namespace)
    cmd = ["argocd", "app", "diff", app_name, *base_args]

    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ARGOCD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("argocd app diff timed out after %ds", ARGOCD_TIMEOUT)
        return ArgoAppDiffResult(success=False, error="Timeout running argocd app diff")
    except FileNotFoundError:
        logger.error("argocd CLI not found on PATH")
        return ArgoAppDiffResult(success=False, error="argocd CLI not found")

    if result.returncode == 0:
        return ArgoAppDiffResult(success=True, in_sync=True)
    elif result.returncode == 1:
        diff_output = result.stdout.strip() or result.stderr.strip()
        return ArgoAppDiffResult(
            success=True,
            in_sync=False,
            diff_output=diff_output,
        )
    else:
        error = result.stderr.strip() or result.stdout.strip()
        logger.warning("argocd app diff error: %s", error)
        return ArgoAppDiffResult(success=False, error=error)
