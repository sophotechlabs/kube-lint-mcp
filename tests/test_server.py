import json
import subprocess

import pytest

from kube_lint_mcp import server

# list_tools tests


@pytest.mark.asyncio
async def test_list_tools_returns_all_tools():
    tools = await server.list_tools()
    names = {t.name for t in tools}

    assert names == {
        "select_kube_context",
        "list_kube_contexts",
        "flux_dryrun",
        "flux_check",
        "flux_status",
        "kustomize_dryrun",
        "helm_dryrun",
        "kubeconform_validate",
        "yaml_validate",
        "argocd_app_list",
        "argocd_app_get",
        "argocd_app_diff",
    }


# select_kube_context tests


@pytest.mark.asyncio
async def test_select_context_requires_list_first():
    result = await server.call_tool("select_kube_context", {"context": "my-ctx"})

    assert "list_kube_contexts" in result[0].text
    assert server._selected_context is None


@pytest.mark.asyncio
async def test_select_context_rejects_immediate_call_after_list():
    """Calling select_kube_context too quickly after list_kube_contexts must fail.

    This enforces that the AI presents the list and waits for user input
    before selecting — not both in the same response.
    """
    import time

    server._contexts_listed_at = time.monotonic()  # just listed — too soon

    result = await server.call_tool("select_kube_context", {"context": "my-ctx"})

    assert "wait for the user" in result[0].text
    assert server._selected_context is None


@pytest.mark.asyncio
async def test_select_context_missing_param():
    server._contexts_listed_at = 0.0
    result = await server.call_tool("select_kube_context", {})

    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_select_context_empty_param():
    server._contexts_listed_at = 0.0
    result = await server.call_tool("select_kube_context", {"context": ""})

    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_select_context_not_found(mocker):
    server._contexts_listed_at = 0.0
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        # get_kubectl_contexts (contexts list)
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        # get_kubectl_contexts (current)
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
    ]

    result = await server.call_tool("select_kube_context", {"context": "nonexistent"})

    assert "not found" in result[0].text.lower()
    assert "ctx-a" in result[0].text


@pytest.mark.asyncio
async def test_select_context_success(mocker):
    server._contexts_listed_at = 0.0
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="my-ctx\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="my-ctx\n", stderr=""
        ),
    ]

    result = await server.call_tool("select_kube_context", {"context": "my-ctx"})

    assert "selected" in result[0].text.lower()
    assert server._selected_context == "my-ctx"


# context requirement tests


@pytest.mark.asyncio
async def test_flux_dryrun_requires_context():
    result = await server.call_tool("flux_dryrun", {"path": "/some/path"})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_flux_check_requires_context():
    result = await server.call_tool("flux_check", {})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_flux_status_requires_context():
    result = await server.call_tool("flux_status", {})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_kustomize_dryrun_requires_context():
    result = await server.call_tool("kustomize_dryrun", {"path": "/some/path"})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_helm_dryrun_requires_context():
    result = await server.call_tool("helm_dryrun", {"chart_path": "/some"})

    assert "select_kube_context" in result[0].text


# parameter validation tests


@pytest.mark.asyncio
async def test_flux_dryrun_missing_path():
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("flux_dryrun", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_kustomize_dryrun_missing_path():
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("kustomize_dryrun", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_kustomize_dryrun_not_a_kustomization(tmp_path):
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})

    assert "not a Kustomize overlay" in result[0].text


@pytest.mark.asyncio
async def test_helm_dryrun_missing_chart_path():
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("helm_dryrun", {})

    assert "chart_path" in result[0].text
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_helm_dryrun_not_a_chart(tmp_path):
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})

    assert "not a Helm chart" in result[0].text


@pytest.mark.asyncio
async def test_unknown_tool():
    result = await server.call_tool("nonexistent", {})

    assert "Unknown tool" in result[0].text


@pytest.mark.asyncio
async def test_none_arguments():
    server._contexts_listed_at = 0.0
    result = await server.call_tool("select_kube_context", None)

    assert "required" in result[0].text.lower()


# list_kube_contexts tests


@pytest.mark.asyncio
async def test_list_contexts_no_contexts(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
    ]

    result = await server.call_tool("list_kube_contexts", {})

    assert "no kubectl contexts" in result[0].text.lower()


@pytest.mark.asyncio
async def test_list_contexts_shows_selected(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
    ]
    server._contexts_listed_at = 0.0
    server._selected_context ="ctx-b"

    result = await server.call_tool("list_kube_contexts", {})

    assert "selected" in result[0].text.lower()
    assert "ctx-b" in result[0].text


# flux_dryrun no files test


@pytest.mark.asyncio
async def test_flux_dryrun_no_yaml_files(tmp_path):
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "readme.md").write_text("hello")

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})

    assert "No YAML files" in result[0].text


# list_kube_contexts — additional coverage


@pytest.mark.asyncio
async def test_list_contexts_no_selected_shows_hint(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\n", stderr=""
        ),
    ]

    result = await server.call_tool("list_kube_contexts", {})

    assert "No context selected" in result[0].text
    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_list_contexts_shows_global_current_marker(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\n", stderr=""
        ),
    ]

    result = await server.call_tool("list_kube_contexts", {})

    assert "(global current)" in result[0].text


# flux_dryrun integration tests


@pytest.mark.asyncio
async def test_flux_dryrun_all_pass(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Client dry-run: PASS" in text
    assert "Server dry-run: PASS" in text
    assert "1 passed, 0 failed" in text
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_flux_dryrun_client_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "bad.yaml").write_text("apiVersion: v1\nkind: Bad\n")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid resource"
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Client dry-run: FAIL" in text
    assert "error: invalid resource" in text
    assert "0 passed, 1 failed" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_flux_dryrun_server_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: forbidden"
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Client dry-run: PASS" in text
    assert "Server dry-run: FAIL" in text
    assert "error: forbidden" in text
    assert "0 passed, 1 failed" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_flux_dryrun_server_pass_with_warnings(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="configured\n",
            stderr="Warning: policy/v1beta1 PodSecurityPolicy is deprecated",
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "PASS (with warnings)" in text
    assert "Warning:" in text
    assert "deprecated" in text.lower()
    assert "1 passed, 0 failed" in text
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_flux_dryrun_mixed_results(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "a.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")
    (tmp_path / "b.yaml").write_text("apiVersion: v1\nkind: Bad\n")

    mock_run.side_effect = [
        # a.yaml client pass
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # a.yaml server pass
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # b.yaml client fail
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid"
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "1 passed, 1 failed" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_flux_dryrun_shows_context_and_path(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="prod-cluster"
    (tmp_path / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Context: prod-cluster" in text
    assert f"Path: {tmp_path}" in text


# flux_check integration tests


@pytest.mark.asyncio
async def test_flux_check_healthy(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="all checks passed\n", stderr=""
    )

    result = await server.call_tool("flux_check", {})
    text = result[0].text

    assert "HEALTHY" in text
    assert "Context: test-ctx" in text
    assert "all checks passed" in text


@pytest.mark.asyncio
async def test_flux_check_unhealthy(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="flux-system check failed\n"
    )

    result = await server.call_tool("flux_check", {})
    text = result[0].text

    assert "UNHEALTHY" in text
    assert "Context: test-ctx" in text


# flux_status integration tests


@pytest.mark.asyncio
async def test_flux_status_success(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="NAME\tREADY\nkustomization/flux-system\tTrue\n",
        stderr="",
    )

    result = await server.call_tool("flux_status", {})
    text = result[0].text

    assert "Flux Status:" in text
    assert "Context: test-ctx" in text
    assert "kustomization/flux-system" in text


@pytest.mark.asyncio
async def test_flux_status_failure(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="error: flux not ready\n"
    )

    result = await server.call_tool("flux_status", {})
    text = result[0].text

    assert "Error getting Flux status" in text
    assert "Context: test-ctx" in text


# kustomize_dryrun integration tests


KUSTOMIZE_RENDERED_YAML = """\
apiVersion: v1
kind: Namespace
metadata:
  name: production
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: production
data:
  key: value
"""


@pytest.mark.asyncio
async def test_kustomize_dryrun_all_pass(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

    mock_run.side_effect = [
        # kubectl kustomize
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=KUSTOMIZE_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # kubectl server dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Kustomize build: PASS (2 resources)" in text
    assert "Client dry-run: PASS" in text
    assert "Server dry-run: PASS" in text
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_kustomize_dryrun_build_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "kustomization.yaml").write_text("resources: [missing.yaml]")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: missing.yaml not found"
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Kustomize build: FAIL" in text
    assert "missing.yaml" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_kustomize_dryrun_client_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=KUSTOMIZE_RENDERED_YAML, stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid manifest"
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Kustomize build: PASS" in text
    assert "Client dry-run: FAIL" in text
    assert "invalid manifest" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_kustomize_dryrun_server_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=KUSTOMIZE_RENDERED_YAML, stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: forbidden"
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Server dry-run: FAIL" in text
    assert "forbidden" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_kustomize_dryrun_server_pass_with_warnings(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=KUSTOMIZE_RENDERED_YAML, stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="configured\n",
            stderr="Warning: policy/v1beta1 PodSecurityPolicy is deprecated",
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "PASS (with warnings)" in text
    assert "Warning:" in text
    assert "deprecated" in text.lower()
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_kustomize_dryrun_shows_context_and_path(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="prod-cluster"
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=KUSTOMIZE_RENDERED_YAML, stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})
    text = result[0].text

    assert "Context: prod-cluster" in text
    assert f"Path: {tmp_path}" in text


# helm_dryrun integration tests


HELM_RENDERED_YAML = """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
---
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""


@pytest.mark.asyncio
async def test_helm_dryrun_all_pass(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1 chart(s) linted\n", stderr=""
        ),
        # helm template
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # kubectl server dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "Helm lint: PASS" in text
    assert "Helm template: PASS (2 resources)" in text
    assert "Client dry-run: PASS" in text
    assert "Server dry-run: PASS" in text
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_helm_dryrun_lint_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint fails
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="[ERROR] templates/: parse error"
        ),
        # helm template still runs
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # kubectl server dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "Helm lint: FAIL" in text
    assert "parse error" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_helm_dryrun_render_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint passes
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        ),
        # helm template fails
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: template rendering failed"
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "Helm lint: PASS" in text
    assert "Helm template: FAIL" in text
    assert "template rendering failed" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_helm_dryrun_client_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        ),
        # helm template
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run fails
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid manifest"
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "Client dry-run: FAIL" in text
    assert "invalid manifest" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_helm_dryrun_server_fail(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        ),
        # helm template
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run passes
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # kubectl server dry-run fails
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: forbidden"
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "Server dry-run: FAIL" in text
    assert "forbidden" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_helm_dryrun_server_pass_with_warnings(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")

    mock_run.side_effect = [
        # helm lint
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        ),
        # helm template
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        # kubectl client dry-run
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        # kubectl server dry-run with deprecation
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="configured\n",
            stderr="Warning: batch/v1beta1 CronJob is deprecated",
        ),
    ]

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})
    text = result[0].text

    assert "PASS (with warnings)" in text
    assert "Warning:" in text
    assert "deprecated" in text.lower()
    assert "Safe to commit" in text


@pytest.mark.asyncio
async def test_helm_dryrun_shows_values_and_namespace(mocker, tmp_path):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"
    (tmp_path / "Chart.yaml").write_text("name: test-chart\nversion: 0.1.0\n")
    values_file = str(tmp_path / "values-prod.yaml")

    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=HELM_RENDERED_YAML, stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = await server.call_tool(
        "helm_dryrun",
        {
            "chart_path": str(tmp_path),
            "values_file": values_file,
            "namespace": "production",
        },
    )
    text = result[0].text

    assert f"Values: {values_file}" in text
    assert "Namespace: production" in text


# path normalization tests


def test_normalize_path_expands_tilde():
    result = server._normalize_path("~/k8s")
    assert "~" not in result
    assert result.startswith("/")


def test_normalize_path_resolves_relative():
    result = server._normalize_path("./manifests")
    assert result.startswith("/")
    assert "/." not in result


# kubeconform_validate integration tests


def _kubeconform_resource(
    status="statusValid", kind="Deployment", name="my-app",
    version="apps/v1", filename="deploy.yaml", msg="",
):
    return json.dumps({
        "filename": filename, "kind": kind, "name": name,
        "version": version, "status": status, "msg": msg,
    })


@pytest.mark.asyncio
async def test_kubeconform_missing_path():
    result = await server.call_tool("kubeconform_validate", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_kubeconform_works_without_context(mocker):
    mock_run = mocker.patch("subprocess.run")
    """Key differentiator: kubeconform does NOT require select_kube_context."""
    server._contexts_listed_at = 0.0
    server._selected_context =None
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool("kubeconform_validate", {"path": "/tmp/test"})

    assert "Error: No context selected" not in result[0].text
    assert "Kubeconform Schema Validation" in result[0].text


@pytest.mark.asyncio
async def test_kubeconform_all_valid(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = "\n".join([
        _kubeconform_resource(),
        _kubeconform_resource(kind="Service", name="my-svc", version="v1"),
    ])
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr="",
    )

    result = await server.call_tool("kubeconform_validate", {"path": "/tmp/test"})
    text = result[0].text

    assert "PASS" in text
    assert "Safe to commit" in text
    assert "2 valid, 0 invalid" in text


@pytest.mark.asyncio
async def test_kubeconform_has_invalid(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = "\n".join([
        _kubeconform_resource(),
        _kubeconform_resource(
            status="statusInvalid", name="bad",
            msg="spec.replicas: Invalid type. Expected: integer, given: string",
        ),
    ])
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=stdout, stderr="",
    )

    result = await server.call_tool("kubeconform_validate", {"path": "/tmp/test"})
    text = result[0].text

    assert "INVALID" in text
    assert "DO NOT COMMIT" in text
    assert "spec.replicas" in text


@pytest.mark.asyncio
async def test_kubeconform_shows_path(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/my/manifests"},
    )
    text = result[0].text

    assert "Path: /my/manifests" in text


@pytest.mark.asyncio
async def test_kubeconform_shows_kubernetes_version(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate",
        {"path": "/tmp/test", "kubernetes_version": "1.29.0"},
    )
    text = result[0].text

    assert "Kubernetes version: 1.29.0" in text


@pytest.mark.asyncio
async def test_kubeconform_shows_strict_mode(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate",
        {"path": "/tmp/test", "strict": True},
    )
    text = result[0].text

    assert "Strict mode: enabled" in text


@pytest.mark.asyncio
async def test_kubeconform_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = FileNotFoundError("kubeconform")

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "kubeconform not found" in text


@pytest.mark.asyncio
async def test_kubeconform_no_resources(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "No resources found" in text


@pytest.mark.asyncio
async def test_kubeconform_shows_error_resources(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = _kubeconform_resource(
        status="statusError", msg="could not download schema",
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=stdout, stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "ERROR" in text
    assert "could not download schema" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_kubeconform_shows_skipped_resources(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = _kubeconform_resource(
        status="statusSkipped", kind="MyCRD", name="x",
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "SKIPPED" in text
    assert "Safe to commit" in text


# yaml_validate integration tests


@pytest.mark.asyncio
async def test_yaml_validate_missing_path():
    result = await server.call_tool("yaml_validate", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_yaml_validate_works_without_context():
    """yaml_validate does NOT require select_kube_context."""
    server._contexts_listed_at = 0.0
    server._selected_context =None

    result = await server.call_tool("yaml_validate", {"path": "/tmp/nonexistent"})

    assert "Error: No context selected" not in result[0].text
    assert "YAML Syntax Validation" in result[0].text


@pytest.mark.asyncio
async def test_yaml_validate_no_files(tmp_path):
    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "No YAML files found" in text


@pytest.mark.asyncio
async def test_yaml_validate_all_valid(tmp_path):
    (tmp_path / "a.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")
    (tmp_path / "b.yaml").write_text("key: value\n")

    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "PASS" in text
    assert "2 valid, 0 invalid" in text
    assert "All YAML files are syntactically valid" in text


@pytest.mark.asyncio
async def test_yaml_validate_has_invalid(tmp_path):
    (tmp_path / "good.yaml").write_text("key: value\n")
    (tmp_path / "bad.yaml").write_text("key: [\n  unclosed\n")

    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "FAIL" in text
    assert "1 valid, 1 invalid" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_yaml_validate_duplicate_key(tmp_path):
    (tmp_path / "dup.yaml").write_text("key: value1\nkey: value2\n")

    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "FAIL" in text
    assert "duplicate" in text.lower()


@pytest.mark.asyncio
async def test_yaml_validate_valid_with_tab_warnings(mocker, tmp_path):
    """Hits the 'PASS with warnings' formatter branch."""
    from kube_lint_mcp import yaml_lint

    fake_result = yaml_lint.YamlValidationResult(
        path=str(tmp_path),
        passed=True,
        files=[
            yaml_lint.YamlFileResult(
                file=str(tmp_path / "tabs.yaml"),
                valid=True,
                warnings=["line 2: tab character used for indentation"],
                document_count=1,
            ),
        ],
        total_files=1,
        valid_files=1,
        invalid_files=0,
    )

    mocker.patch("kube_lint_mcp.yaml_lint.validate_yaml", return_value=fake_result)
    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "PASS with warnings" in text
    assert "Warning" in text
    assert "tab" in text.lower()


@pytest.mark.asyncio
async def test_yaml_validate_fail_with_warnings(mocker, tmp_path):
    """Hits the FAIL branch that also has warnings (errors + warnings on same file)."""
    from kube_lint_mcp import yaml_lint

    fake_result = yaml_lint.YamlValidationResult(
        path=str(tmp_path),
        passed=False,
        files=[
            yaml_lint.YamlFileResult(
                file=str(tmp_path / "bad.yaml"),
                valid=False,
                errors=["line 3, column 1: syntax error"],
                warnings=["line 1: tab character used for indentation"],
                document_count=0,
            ),
        ],
        total_files=1,
        valid_files=0,
        invalid_files=1,
    )

    mocker.patch("kube_lint_mcp.yaml_lint.validate_yaml", return_value=fake_result)
    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert "FAIL" in text
    assert "Error: line 3" in text
    assert "Warning: line 1" in text
    assert "DO NOT COMMIT" in text


@pytest.mark.asyncio
async def test_yaml_validate_shows_path(tmp_path):
    result = await server.call_tool("yaml_validate", {"path": str(tmp_path)})
    text = result[0].text

    assert f"Path: {tmp_path}" in text


@pytest.mark.asyncio
async def test_yaml_validate_single_file(tmp_path):
    f = tmp_path / "deploy.yaml"
    f.write_text("apiVersion: v1\nkind: ConfigMap\n")

    result = await server.call_tool("yaml_validate", {"path": str(f)})
    text = result[0].text

    assert "1 valid, 0 invalid" in text
    assert "PASS" in text


# argocd_app_list integration tests

# Simulates successful namespace auto-detection (kubectl get configmap argocd-cm)
_DETECT_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="argocd", stderr="")

ARGOCD_LIST_JSON = json.dumps([
    {
        "metadata": {"name": "my-app", "namespace": "argocd"},
        "spec": {
            "project": "default",
            "source": {
                "repoURL": "https://github.com/org/repo.git",
                "path": "k8s/app",
                "targetRevision": "HEAD",
            },
        },
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
        },
    },
])

ARGOCD_GET_JSON = json.dumps({
    "metadata": {"name": "my-app", "namespace": "argocd"},
    "spec": {
        "project": "default",
        "source": {
            "repoURL": "https://github.com/org/repo.git",
            "path": "k8s/app",
            "targetRevision": "HEAD",
        },
    },
    "status": {
        "sync": {"status": "Synced", "revision": "abc123"},
        "health": {"status": "Healthy"},
        "conditions": [
            {"type": "SyncError", "message": "some sync issue"},
        ],
        "resources": [
            {
                "kind": "Deployment",
                "namespace": "default",
                "name": "my-app",
                "status": "Synced",
                "health": {"status": "Healthy"},
            },
        ],
    },
})

ARGOCD_GET_MINIMAL_JSON = json.dumps({
    "metadata": {"name": "my-app", "namespace": "argocd"},
    "spec": {
        "project": "default",
        "source": {
            "repoURL": "https://github.com/org/repo.git",
            "path": "k8s/app",
            "targetRevision": "HEAD",
        },
    },
    "status": {
        "sync": {"status": "OutOfSync", "revision": "def456"},
        "health": {"status": "Degraded", "message": "container failing"},
    },
})


@pytest.mark.asyncio
async def test_argocd_app_list_requires_context():
    result = await server.call_tool("argocd_app_list", {})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_argocd_app_list_success(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_LIST_JSON, stderr=""),
    ]

    result = await server.call_tool("argocd_app_list", {})
    text = result[0].text

    assert "ArgoCD Application List" in text
    assert "Context: test-ctx" in text
    assert "my-app" in text
    assert "Synced" in text
    assert "Healthy" in text
    assert "Total: 1 application(s)" in text


@pytest.mark.asyncio
async def test_argocd_app_list_empty(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    result = await server.call_tool("argocd_app_list", {})
    text = result[0].text

    assert "No ArgoCD applications found" in text
    assert "Total: 0 application(s)" in text


@pytest.mark.asyncio
async def test_argocd_app_list_with_namespace(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=ARGOCD_LIST_JSON, stderr=""
    )

    result = await server.call_tool("argocd_app_list", {"namespace": "argo-cd"})
    text = result[0].text

    assert "Namespace: argo-cd" in text


@pytest.mark.asyncio
async def test_argocd_app_list_error(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="connection refused"),
    ]

    result = await server.call_tool("argocd_app_list", {})
    text = result[0].text

    assert "Error listing ArgoCD apps" in text
    assert "connection refused" in text


@pytest.mark.asyncio
async def test_argocd_app_list_shows_context(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="prod-cluster"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    result = await server.call_tool("argocd_app_list", {})
    text = result[0].text

    assert "Context: prod-cluster" in text


# argocd_app_get integration tests


@pytest.mark.asyncio
async def test_argocd_app_get_requires_context():
    result = await server.call_tool("argocd_app_get", {"app_name": "my-app"})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_argocd_app_get_missing_app_name():
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("argocd_app_get", {})
    text = result[0].text

    assert "app_name" in text
    assert "required" in text.lower()


@pytest.mark.asyncio
async def test_argocd_app_get_success(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_GET_JSON, stderr=""),
    ]

    result = await server.call_tool("argocd_app_get", {"app_name": "my-app"})
    text = result[0].text

    assert "ArgoCD Application Detail" in text
    assert "Context: test-ctx" in text
    assert "Application: my-app" in text
    assert "Sync Status: Synced" in text
    assert "Health Status: Healthy" in text
    assert "Project: default" in text


@pytest.mark.asyncio
async def test_argocd_app_get_with_resources_and_conditions(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_GET_JSON, stderr=""),
    ]

    result = await server.call_tool("argocd_app_get", {"app_name": "my-app"})
    text = result[0].text

    assert "Conditions:" in text
    assert "SyncError" in text
    assert "Resources:" in text
    assert "Deployment/my-app" in text


@pytest.mark.asyncio
async def test_argocd_app_get_with_health_message(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_GET_MINIMAL_JSON, stderr=""),
    ]

    result = await server.call_tool("argocd_app_get", {"app_name": "my-app"})
    text = result[0].text

    assert "Health Message: container failing" in text
    assert "Sync Revision: def456" in text


@pytest.mark.asyncio
async def test_argocd_app_get_error(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="app 'missing' not found"),
    ]

    result = await server.call_tool("argocd_app_get", {"app_name": "missing"})
    text = result[0].text

    assert "Error getting ArgoCD app" in text
    assert "not found" in text


@pytest.mark.asyncio
async def test_argocd_app_get_shows_context_and_app(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="prod-cluster"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_GET_JSON, stderr=""),
    ]

    result = await server.call_tool(
        "argocd_app_get", {"app_name": "my-app"},
    )
    text = result[0].text

    assert "Context: prod-cluster" in text
    assert "Application: my-app" in text


# argocd_app_diff integration tests


@pytest.mark.asyncio
async def test_argocd_app_diff_requires_context():
    result = await server.call_tool("argocd_app_diff", {"app_name": "my-app"})

    assert "select_kube_context" in result[0].text


@pytest.mark.asyncio
async def test_argocd_app_diff_missing_app_name():
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    result = await server.call_tool("argocd_app_diff", {})
    text = result[0].text

    assert "app_name" in text
    assert "required" in text.lower()


@pytest.mark.asyncio
async def test_argocd_app_diff_in_sync(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    result = await server.call_tool("argocd_app_diff", {"app_name": "my-app"})
    text = result[0].text

    assert "ArgoCD Application Diff" in text
    assert "IN SYNC" in text


@pytest.mark.asyncio
async def test_argocd_app_diff_has_diff(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    diff_output = "===== apps/Deployment default/my-app ======\n  replicas: 2 -> 3"
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout=diff_output, stderr=""),
    ]

    result = await server.call_tool("argocd_app_diff", {"app_name": "my-app"})
    text = result[0].text

    assert "OUT OF SYNC" in text
    assert "replicas" in text


@pytest.mark.asyncio
async def test_argocd_app_diff_error(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="test-ctx"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="FATA[0000] app not found"),
    ]

    result = await server.call_tool("argocd_app_diff", {"app_name": "missing"})
    text = result[0].text

    assert "Error diffing ArgoCD app" in text
    assert "not found" in text


@pytest.mark.asyncio
async def test_argocd_app_diff_shows_context_and_app(mocker):
    mock_run = mocker.patch("subprocess.run")
    server._contexts_listed_at = 0.0
    server._selected_context ="prod-cluster"

    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    result = await server.call_tool(
        "argocd_app_diff", {"app_name": "my-app"},
    )
    text = result[0].text

    assert "Context: prod-cluster" in text
    assert "Application: my-app" in text
