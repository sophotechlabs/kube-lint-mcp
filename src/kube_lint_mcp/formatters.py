"""Output formatting for validation results."""

from kube_lint_mcp import argocd_lint, flux_lint, helm_lint, kubeconform_lint, kustomize_lint, yaml_lint


def format_step(
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


def format_summary(passed: int, failed: int) -> list[str]:
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


def format_flux_results(
    results: list[flux_lint.ValidationResult],
    context: str,
    path: str,
) -> str:
    """Format flux dry-run validation results into output text."""
    lines = [
        "FluxCD Dry-Run Validation",
        f"Context: {context}",
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
            step = format_step("Client dry-run", False, r.client_error)
            lines.extend(["  " + ln for ln in step])
            failed += 1
            lines.append("")
            continue

        if r.server_passed:
            step = format_step("Server dry-run", True, warnings=r.warnings)
            lines.extend(["  " + ln for ln in step])
            passed += 1
        else:
            step = format_step("Server dry-run", False, r.server_error)
            lines.extend(["  " + ln for ln in step])
            failed += 1

        lines.append("")

    lines.extend(format_summary(passed, failed))
    return "\n".join(lines)


def format_kustomize_result(
    result: kustomize_lint.KustomizeValidationResult,
    context: str,
    path: str,
) -> str:
    """Format kustomize validation result into output text."""
    lines = [
        "Kustomize Dry-Run Validation",
        f"Context: {context}",
        f"Path: {path}",
        "=" * 50,
        "",
    ]

    passed = 0
    failed = 0

    if result.build_passed:
        lines.append(f"Kustomize build: PASS ({result.resource_count} resources)")
        passed += 1
    else:
        lines.extend(format_step("Kustomize build", False, result.build_error))
        failed += 1
    lines.append("")

    lines.extend(
        format_step("Client dry-run", result.client_passed, result.client_error)
    )
    if result.client_passed:
        passed += 1
    else:
        failed += 1
    lines.append("")

    lines.extend(
        format_step(
            "Server dry-run", result.server_passed,
            result.server_error, result.warnings,
        )
    )
    if result.server_passed:
        passed += 1
    else:
        failed += 1

    lines.append("")
    lines.extend(format_summary(passed, failed))
    return "\n".join(lines)


def format_helm_result(
    result: helm_lint.HelmValidationResult,
    context: str,
    chart_path: str,
    values_file: str | None,
    namespace: str | None,
) -> str:
    """Format helm chart validation result into output text."""
    lines = [
        "Helm Chart Dry-Run Validation",
        f"Context: {context}",
        f"Chart: {chart_path}",
    ]
    if values_file:
        lines.append(f"Values: {values_file}")
    if namespace:
        lines.append(f"Namespace: {namespace}")
    lines.extend(["=" * 50, ""])

    passed = 0
    failed = 0

    lines.extend(format_step("Helm lint", result.lint_passed, result.lint_error))
    if result.lint_passed:
        passed += 1
    else:
        failed += 1
    lines.append("")

    if result.render_passed:
        lines.append(f"Helm template: PASS ({result.resource_count} resources)")
        passed += 1
    else:
        lines.extend(format_step("Helm template", False, result.render_error))
        failed += 1
    lines.append("")

    lines.extend(
        format_step("Client dry-run", result.client_passed, result.client_error)
    )
    if result.client_passed:
        passed += 1
    else:
        failed += 1
    lines.append("")

    lines.extend(
        format_step(
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
    return "\n".join(lines)


def format_kubeconform_result(
    result: kubeconform_lint.KubeconformResult,
    path: str,
    kubernetes_version: str,
    strict: bool,
) -> str:
    """Format kubeconform validation result into output text."""
    lines = [
        "Kubeconform Schema Validation",
        f"Path: {path}",
    ]
    if kubernetes_version != "master":
        lines.append(f"Kubernetes version: {kubernetes_version}")
    if strict:
        lines.append("Strict mode: enabled")
    lines.extend(["=" * 50, ""])

    if not result.resources:
        lines.append("No resources found to validate.")
    else:
        for r in result.resources:
            label = f"{r.kind}/{r.name}" if r.name else r.kind
            api = f" ({r.version})" if r.version else ""

            if r.status == "statusValid":
                lines.append(f"  {label}{api}: PASS")
            elif r.status == "statusInvalid":
                lines.append(f"  {label}{api}: INVALID")
                if r.msg:
                    for msg_line in r.msg.splitlines():
                        lines.append(f"    {msg_line}")
            elif r.status == "statusError":
                lines.append(f"  {label}{api}: ERROR")
                if r.msg:
                    for msg_line in r.msg.splitlines():
                        lines.append(f"    {msg_line}")
            elif r.status == "statusSkipped":
                lines.append(f"  {label}{api}: SKIPPED")

    lines.append("")
    lines.append("=" * 50)
    lines.append(
        f"Summary: {result.valid} valid, {result.invalid} invalid,"
        f" {result.errors} errors, {result.skipped} skipped"
    )
    lines.append("")

    if result.passed:
        lines.append("All validations passed. Safe to commit.")
    else:
        lines.append("DO NOT COMMIT - Fix schema errors first!")
    return "\n".join(lines)


def format_yaml_result(
    result: yaml_lint.YamlValidationResult,
    path: str,
) -> str:
    """Format YAML validation result into output text."""
    lines = [
        "YAML Syntax Validation",
        f"Path: {path}",
        "=" * 50,
        "",
    ]

    if not result.files:
        lines.append("No YAML files found.")
    else:
        for f in result.files:
            if f.valid and not f.warnings:
                lines.append(f"  {f.file}: PASS ({f.document_count} documents)")
            elif f.valid and f.warnings:
                lines.append(f"  {f.file}: PASS with warnings ({f.document_count} documents)")
                for w in f.warnings:
                    lines.append(f"    Warning: {w}")
            else:
                lines.append(f"  {f.file}: FAIL")
                for e in f.errors:
                    lines.append(f"    Error: {e}")
                for w in f.warnings:
                    lines.append(f"    Warning: {w}")
            lines.append("")

    lines.append("=" * 50)
    lines.append(
        f"Summary: {result.valid_files} valid, {result.invalid_files} invalid"
        f" ({result.total_files} files)"
    )
    lines.append("")

    if result.passed:
        lines.append("All YAML files are syntactically valid.")
    else:
        lines.append("DO NOT COMMIT - Fix YAML syntax errors first!")
    return "\n".join(lines)


def format_argocd_app_list_result(
    result: argocd_lint.ArgoAppListResult,
    context: str,
    namespace: str | None,
) -> str:
    """Format ArgoCD app list result into output text."""
    lines = [
        "ArgoCD Application List",
        f"Context: {context}",
    ]
    if namespace:
        lines.append(f"Namespace: {namespace}")
    lines.extend(["=" * 50, ""])

    if not result.apps:
        lines.append("No ArgoCD applications found.")
    else:
        for app in result.apps:
            lines.append(f"  {app.name}")
            lines.append(f"    Project: {app.project}")
            lines.append(f"    Sync: {app.sync_status}  Health: {app.health_status}")
            lines.append(f"    Repo: {app.repo_url}")
            if app.path:
                lines.append(f"    Path: {app.path}")
            if app.target_revision:
                lines.append(f"    Revision: {app.target_revision}")
            lines.append("")

    lines.append("=" * 50)
    lines.append(f"Total: {len(result.apps)} application(s)")
    return "\n".join(lines)


def format_argocd_app_get_result(
    result: argocd_lint.ArgoAppGetResult,
    context: str,
) -> str:
    """Format ArgoCD app get result into output text."""
    lines = [
        "ArgoCD Application Detail",
        f"Context: {context}",
        f"Application: {result.name}",
        "=" * 50,
        "",
        f"  Project: {result.project}",
        f"  Namespace: {result.namespace}",
        f"  Sync Status: {result.sync_status}",
        f"  Health Status: {result.health_status}",
    ]
    if result.sync_message:
        lines.append(f"  Sync Revision: {result.sync_message}")
    if result.health_message:
        lines.append(f"  Health Message: {result.health_message}")
    lines.extend([
        f"  Repo: {result.repo_url}",
        f"  Path: {result.path}",
        f"  Revision: {result.target_revision}",
        "",
    ])

    if result.conditions:
        lines.append("Conditions:")
        for cond in result.conditions:
            lines.append(f"  - {cond}")
        lines.append("")

    if result.resources:
        lines.append("Resources:")
        for r in result.resources:
            health = r.get("health", "")
            status_str = r.get("status", "")
            label = f"{r.get('kind', '')}/{r.get('name', '')}"
            ns = r.get("namespace", "")
            if ns:
                label = f"{label} ({ns})"
            lines.append(f"  {label}: sync={status_str} health={health}")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


def format_argocd_app_diff_result(
    result: argocd_lint.ArgoAppDiffResult,
    context: str,
    app_name: str,
) -> str:
    """Format ArgoCD app diff result into output text."""
    lines = [
        "ArgoCD Application Diff",
        f"Context: {context}",
        f"Application: {app_name}",
        "=" * 50,
        "",
    ]

    if result.in_sync:
        lines.append("Application is IN SYNC - no differences between live and desired state.")
    else:
        lines.append("Application is OUT OF SYNC - differences detected:")
        lines.append("")
        lines.append(result.diff_output)

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)
