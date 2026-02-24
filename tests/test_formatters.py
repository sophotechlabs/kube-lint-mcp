from kube_lint_mcp import argocd_lint, flux_lint, formatters, helm_lint, kubeconform_lint, kustomize_lint, yaml_lint

# format_step tests


def test_format_step_pass():
    """Should return single PASS line."""
    result = formatters.format_step("Client dry-run", True)

    expected = ["Client dry-run: PASS"]
    assert result == expected


def test_format_step_pass_with_warnings():
    """Should return PASS with warning lines."""
    result = formatters.format_step(
        "Server dry-run", True, warnings=["deprecated API version"],
    )

    assert result[0] == "Server dry-run: PASS (with warnings)"
    assert "  Warning: deprecated API version" in result


def test_format_step_fail():
    """Should return FAIL line."""
    result = formatters.format_step("Client dry-run", False)

    expected = ["Client dry-run: FAIL"]
    assert result == expected


def test_format_step_fail_with_error():
    """Should return FAIL line with error detail."""
    result = formatters.format_step("Client dry-run", False, error="invalid resource")

    expected = ["Client dry-run: FAIL", "  Error: invalid resource"]
    assert result == expected


# format_summary tests


def test_format_summary_all_passed():
    """Should show safe to commit when no failures."""
    result = formatters.format_summary(3, 0)

    assert "3 passed, 0 failed" in result[1]
    assert "Safe to commit" in result[-1]


def test_format_summary_has_failures():
    """Should show DO NOT COMMIT when failures exist."""
    result = formatters.format_summary(1, 2)

    assert "1 passed, 2 failed" in result[1]
    assert "DO NOT COMMIT" in result[-1]


# format_flux_results tests


def test_format_flux_results_all_pass():
    """Should format all-passing flux results."""
    results = [
        flux_lint.ValidationResult(
            file="deploy.yaml", client_passed=True, server_passed=True,
        ),
    ]

    output = formatters.format_flux_results(results, "test-ctx", "/tmp/manifests")

    assert "FluxCD Dry-Run Validation" in output
    assert "Context: test-ctx" in output
    assert "Path: /tmp/manifests" in output
    assert "Client dry-run: PASS" in output
    assert "Server dry-run: PASS" in output
    assert "1 passed, 0 failed" in output
    assert "Safe to commit" in output


def test_format_flux_results_client_fail():
    """Should format client failure and skip server check."""
    results = [
        flux_lint.ValidationResult(
            file="bad.yaml", client_passed=False, server_passed=False,
            client_error="invalid resource",
        ),
    ]

    output = formatters.format_flux_results(results, "ctx", "/tmp")

    assert "Client dry-run: FAIL" in output
    assert "invalid resource" in output
    assert "0 passed, 1 failed" in output
    assert "DO NOT COMMIT" in output


def test_format_flux_results_server_fail():
    """Should format server failure after client pass."""
    results = [
        flux_lint.ValidationResult(
            file="deploy.yaml", client_passed=True, server_passed=False,
            server_error="forbidden",
        ),
    ]

    output = formatters.format_flux_results(results, "ctx", "/tmp")

    assert "Client dry-run: PASS" in output
    assert "Server dry-run: FAIL" in output
    assert "forbidden" in output
    assert "0 passed, 1 failed" in output


def test_format_flux_results_server_pass_with_warnings():
    """Should format server pass with deprecation warnings."""
    results = [
        flux_lint.ValidationResult(
            file="deploy.yaml", client_passed=True, server_passed=True,
            warnings=["policy/v1beta1 PodSecurityPolicy is deprecated"],
        ),
    ]

    output = formatters.format_flux_results(results, "ctx", "/tmp")

    assert "PASS (with warnings)" in output
    assert "deprecated" in output
    assert "1 passed, 0 failed" in output


def test_format_flux_results_mixed():
    """Should correctly count mixed pass/fail results."""
    results = [
        flux_lint.ValidationResult(
            file="good.yaml", client_passed=True, server_passed=True,
        ),
        flux_lint.ValidationResult(
            file="bad.yaml", client_passed=False, server_passed=False,
            client_error="invalid",
        ),
    ]

    output = formatters.format_flux_results(results, "ctx", "/tmp")

    assert "1 passed, 1 failed" in output
    assert "DO NOT COMMIT" in output


# format_kustomize_result tests


def test_format_kustomize_result_all_pass():
    """Should format all-passing kustomize result."""
    result = kustomize_lint.KustomizeValidationResult(
        path="/tmp/overlay", build_passed=True, client_passed=True,
        server_passed=True, resource_count=5,
    )

    output = formatters.format_kustomize_result(result, "test-ctx", "/tmp/overlay")

    assert "Kustomize Dry-Run Validation" in output
    assert "Kustomize build: PASS (5 resources)" in output
    assert "Client dry-run: PASS" in output
    assert "Server dry-run: PASS" in output
    assert "3 passed, 0 failed" in output
    assert "Safe to commit" in output


def test_format_kustomize_result_build_fail():
    """Should format build failure."""
    result = kustomize_lint.KustomizeValidationResult(
        path="/tmp", build_passed=False, client_passed=False,
        server_passed=False, build_error="missing.yaml not found",
    )

    output = formatters.format_kustomize_result(result, "ctx", "/tmp")

    assert "Kustomize build: FAIL" in output
    assert "missing.yaml" in output
    assert "DO NOT COMMIT" in output


def test_format_kustomize_result_server_warnings():
    """Should format server pass with warnings."""
    result = kustomize_lint.KustomizeValidationResult(
        path="/tmp", build_passed=True, client_passed=True,
        server_passed=True, resource_count=2,
        warnings=["deprecated API"],
    )

    output = formatters.format_kustomize_result(result, "ctx", "/tmp")

    assert "PASS (with warnings)" in output
    assert "deprecated API" in output
    assert "Safe to commit" in output


# format_helm_result tests


def test_format_helm_result_all_pass():
    """Should format all-passing helm result."""
    result = helm_lint.HelmValidationResult(
        chart_path="/tmp/chart", lint_passed=True, render_passed=True,
        client_passed=True, server_passed=True, resource_count=3,
    )

    output = formatters.format_helm_result(result, "ctx", "/tmp/chart", None, None)

    assert "Helm Chart Dry-Run Validation" in output
    assert "Helm lint: PASS" in output
    assert "Helm template: PASS (3 resources)" in output
    assert "Client dry-run: PASS" in output
    assert "Server dry-run: PASS" in output
    assert "Safe to commit" in output


def test_format_helm_result_shows_values_and_namespace():
    """Should include values file and namespace when provided."""
    result = helm_lint.HelmValidationResult(
        chart_path="/tmp/chart", lint_passed=True, render_passed=True,
        client_passed=True, server_passed=True, resource_count=1,
    )

    output = formatters.format_helm_result(
        result, "ctx", "/tmp/chart", "/tmp/values.yaml", "production",
    )

    assert "Values: /tmp/values.yaml" in output
    assert "Namespace: production" in output


def test_format_helm_result_lint_fail():
    """Should format lint failure."""
    result = helm_lint.HelmValidationResult(
        chart_path="/tmp/chart", lint_passed=False, render_passed=True,
        client_passed=True, server_passed=True, resource_count=1,
        lint_error="parse error",
    )

    output = formatters.format_helm_result(result, "ctx", "/tmp/chart", None, None)

    assert "Helm lint: FAIL" in output
    assert "parse error" in output
    assert "DO NOT COMMIT" in output


def test_format_helm_result_render_fail():
    """Should format render failure."""
    result = helm_lint.HelmValidationResult(
        chart_path="/tmp/chart", lint_passed=True, render_passed=False,
        client_passed=False, server_passed=False,
        render_error="template rendering failed",
    )

    output = formatters.format_helm_result(result, "ctx", "/tmp/chart", None, None)

    assert "Helm template: FAIL" in output
    assert "template rendering failed" in output
    assert "DO NOT COMMIT" in output


# format_kubeconform_result tests


def test_format_kubeconform_result_all_valid():
    """Should format all-valid resources."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=2, invalid=0, errors=0, skipped=0,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="deploy.yaml", kind="Deployment", name="my-app",
                version="apps/v1", status="statusValid",
            ),
            kubeconform_lint.KubeconformResourceResult(
                filename="svc.yaml", kind="Service", name="my-svc",
                version="v1", status="statusValid",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "Kubeconform Schema Validation" in output
    assert "Deployment/my-app (apps/v1): PASS" in output
    assert "Service/my-svc (v1): PASS" in output
    assert "2 valid, 0 invalid" in output
    assert "Safe to commit" in output


def test_format_kubeconform_result_shows_version_and_strict():
    """Should show kubernetes version and strict mode when set."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=0, invalid=0, errors=0, skipped=0,
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "1.29.0", True)

    assert "Kubernetes version: 1.29.0" in output
    assert "Strict mode: enabled" in output


def test_format_kubeconform_result_hides_default_version():
    """Should not show kubernetes version when 'master'."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=0, invalid=0, errors=0, skipped=0,
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "Kubernetes version:" not in output


def test_format_kubeconform_result_has_invalid():
    """Should show INVALID resources with error messages."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=False, valid=0, invalid=1, errors=0, skipped=0,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="bad.yaml", kind="Deployment", name="bad",
                version="apps/v1", status="statusInvalid",
                msg="spec.replicas: Invalid type",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "INVALID" in output
    assert "spec.replicas" in output
    assert "DO NOT COMMIT" in output


def test_format_kubeconform_result_has_error():
    """Should show ERROR resources."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=False, valid=0, invalid=0, errors=1, skipped=0,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="err.yaml", kind="Custom", name="x",
                version="v1", status="statusError",
                msg="could not download schema",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "ERROR" in output
    assert "could not download schema" in output
    assert "DO NOT COMMIT" in output


def test_format_kubeconform_result_has_skipped():
    """Should show SKIPPED resources."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=0, invalid=0, errors=0, skipped=1,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="crd.yaml", kind="MyCRD", name="x",
                version="v1", status="statusSkipped",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "SKIPPED" in output
    assert "Safe to commit" in output


def test_format_kubeconform_result_no_resources():
    """Should show no resources message."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=0, invalid=0, errors=0, skipped=0,
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "No resources found" in output


def test_format_kubeconform_result_resource_without_name():
    """Should format resource label correctly when name is empty."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=1, invalid=0, errors=0, skipped=0,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="f.yaml", kind="Namespace", name="",
                version="v1", status="statusValid",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "Namespace (v1): PASS" in output


def test_format_kubeconform_result_resource_without_version():
    """Should format resource label without API version when empty."""
    result = kubeconform_lint.KubeconformResult(
        path="/tmp", passed=True, valid=1, invalid=0, errors=0, skipped=0,
        resources=[
            kubeconform_lint.KubeconformResourceResult(
                filename="f.yaml", kind="Thing", name="x",
                version="", status="statusValid",
            ),
        ],
    )

    output = formatters.format_kubeconform_result(result, "/tmp", "master", False)

    assert "Thing/x: PASS" in output
    assert "()" not in output


# format_yaml_result tests


def test_format_yaml_result_all_valid():
    """Should format all-valid YAML files."""
    result = yaml_lint.YamlValidationResult(
        path="/tmp", passed=True, total_files=2, valid_files=2, invalid_files=0,
        files=[
            yaml_lint.YamlFileResult(file="a.yaml", valid=True, document_count=1),
            yaml_lint.YamlFileResult(file="b.yaml", valid=True, document_count=2),
        ],
    )

    output = formatters.format_yaml_result(result, "/tmp")

    assert "YAML Syntax Validation" in output
    assert "a.yaml: PASS (1 documents)" in output
    assert "b.yaml: PASS (2 documents)" in output
    assert "2 valid, 0 invalid (2 files)" in output
    assert "All YAML files are syntactically valid" in output


def test_format_yaml_result_has_invalid():
    """Should format invalid files with errors."""
    result = yaml_lint.YamlValidationResult(
        path="/tmp", passed=False, total_files=1, valid_files=0, invalid_files=1,
        files=[
            yaml_lint.YamlFileResult(
                file="bad.yaml", valid=False,
                errors=["line 3: syntax error"],
            ),
        ],
    )

    output = formatters.format_yaml_result(result, "/tmp")

    assert "bad.yaml: FAIL" in output
    assert "Error: line 3: syntax error" in output
    assert "DO NOT COMMIT" in output


def test_format_yaml_result_valid_with_warnings():
    """Should show PASS with warnings for valid files that have warnings."""
    result = yaml_lint.YamlValidationResult(
        path="/tmp", passed=True, total_files=1, valid_files=1, invalid_files=0,
        files=[
            yaml_lint.YamlFileResult(
                file="tabs.yaml", valid=True, document_count=1,
                warnings=["tab used for indentation"],
            ),
        ],
    )

    output = formatters.format_yaml_result(result, "/tmp")

    assert "PASS with warnings" in output
    assert "Warning: tab used for indentation" in output


def test_format_yaml_result_fail_with_warnings():
    """Should show both errors and warnings on failed files."""
    result = yaml_lint.YamlValidationResult(
        path="/tmp", passed=False, total_files=1, valid_files=0, invalid_files=1,
        files=[
            yaml_lint.YamlFileResult(
                file="bad.yaml", valid=False,
                errors=["syntax error"],
                warnings=["tab indentation"],
            ),
        ],
    )

    output = formatters.format_yaml_result(result, "/tmp")

    assert "FAIL" in output
    assert "Error: syntax error" in output
    assert "Warning: tab indentation" in output


def test_format_yaml_result_no_files():
    """Should show no files message."""
    result = yaml_lint.YamlValidationResult(
        path="/tmp", passed=True, total_files=0, valid_files=0, invalid_files=0,
    )

    output = formatters.format_yaml_result(result, "/tmp")

    assert "No YAML files found" in output


# format_argocd_app_list_result tests


def test_format_argocd_app_list_result_with_apps():
    """Should format application list with details."""
    result = argocd_lint.ArgoAppListResult(
        success=True,
        apps=[
            argocd_lint.ArgoAppSummary(
                name="my-app", namespace="argocd", project="default",
                sync_status="Synced", health_status="Healthy",
                repo_url="https://github.com/org/repo.git",
                path="k8s/app", target_revision="HEAD",
            ),
        ],
    )

    output = formatters.format_argocd_app_list_result(result, "test-ctx", None)

    assert "ArgoCD Application List" in output
    assert "Context: test-ctx" in output
    assert "my-app" in output
    assert "Synced" in output
    assert "Healthy" in output
    assert "Total: 1 application(s)" in output


def test_format_argocd_app_list_result_empty():
    """Should show no applications message."""
    result = argocd_lint.ArgoAppListResult(success=True)

    output = formatters.format_argocd_app_list_result(result, "ctx", None)

    assert "No ArgoCD applications found" in output
    assert "Total: 0 application(s)" in output


def test_format_argocd_app_list_result_with_namespace():
    """Should show namespace when provided."""
    result = argocd_lint.ArgoAppListResult(success=True)

    output = formatters.format_argocd_app_list_result(result, "ctx", "argo-cd")

    assert "Namespace: argo-cd" in output


def test_format_argocd_app_list_result_app_without_path():
    """Should omit path when empty."""
    result = argocd_lint.ArgoAppListResult(
        success=True,
        apps=[
            argocd_lint.ArgoAppSummary(
                name="app", namespace="argocd", project="default",
                sync_status="Synced", health_status="Healthy",
                repo_url="https://example.com", path="", target_revision="",
            ),
        ],
    )

    output = formatters.format_argocd_app_list_result(result, "ctx", None)

    assert "Path:" not in output
    assert "Revision:" not in output


# format_argocd_app_get_result tests


def test_format_argocd_app_get_result_full():
    """Should format full app detail with conditions and resources."""
    result = argocd_lint.ArgoAppGetResult(
        success=True, name="my-app", namespace="argocd", project="default",
        sync_status="Synced", health_status="Healthy",
        sync_message="abc123", health_message="",
        repo_url="https://github.com/org/repo.git",
        path="k8s/app", target_revision="HEAD",
        conditions=["SyncError: some issue"],
        resources=[
            {"kind": "Deployment", "namespace": "default", "name": "my-app",
             "status": "Synced", "health": "Healthy"},
        ],
    )

    output = formatters.format_argocd_app_get_result(result, "test-ctx")

    assert "ArgoCD Application Detail" in output
    assert "Application: my-app" in output
    assert "Sync Status: Synced" in output
    assert "Sync Revision: abc123" in output
    assert "Conditions:" in output
    assert "SyncError: some issue" in output
    assert "Resources:" in output
    assert "Deployment/my-app (default)" in output


def test_format_argocd_app_get_result_minimal():
    """Should format minimal app detail without optional fields."""
    result = argocd_lint.ArgoAppGetResult(
        success=True, name="app", namespace="argocd", project="default",
        sync_status="OutOfSync", health_status="Degraded",
        health_message="container failing",
        repo_url="https://example.com", path=".", target_revision="HEAD",
    )

    output = formatters.format_argocd_app_get_result(result, "ctx")

    assert "Health Message: container failing" in output
    assert "Conditions:" not in output
    assert "Resources:" not in output


def test_format_argocd_app_get_result_resource_without_namespace():
    """Should format resource without namespace parenthetical."""
    result = argocd_lint.ArgoAppGetResult(
        success=True, name="app", namespace="argocd", project="default",
        sync_status="Synced", health_status="Healthy",
        repo_url="https://example.com", path=".", target_revision="HEAD",
        resources=[
            {"kind": "ClusterRole", "name": "admin", "status": "Synced", "health": "Healthy"},
        ],
    )

    output = formatters.format_argocd_app_get_result(result, "ctx")

    assert "ClusterRole/admin: sync=Synced health=Healthy" in output
    assert "()" not in output


# format_argocd_app_diff_result tests


def test_format_argocd_app_diff_result_in_sync():
    """Should show in-sync message."""
    result = argocd_lint.ArgoAppDiffResult(success=True, in_sync=True)

    output = formatters.format_argocd_app_diff_result(result, "ctx", "my-app")

    assert "ArgoCD Application Diff" in output
    assert "Application: my-app" in output
    assert "IN SYNC" in output


def test_format_argocd_app_diff_result_out_of_sync():
    """Should show diff output when out of sync."""
    result = argocd_lint.ArgoAppDiffResult(
        success=True, in_sync=False,
        diff_output="--- live\n+++ desired\n-replicas: 1\n+replicas: 3",
    )

    output = formatters.format_argocd_app_diff_result(result, "ctx", "my-app")

    assert "OUT OF SYNC" in output
    assert "--- live" in output
    assert "+replicas: 3" in output
