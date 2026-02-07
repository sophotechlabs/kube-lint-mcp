import json
import subprocess
from unittest import mock

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
    }


# select_kube_context tests


@pytest.mark.asyncio
async def test_select_context_missing_param():
    result = await server.call_tool("select_kube_context", {})

    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_select_context_empty_param():
    result = await server.call_tool("select_kube_context", {"context": ""})

    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_select_context_not_found(mock_run):
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
@mock.patch("subprocess.run")
async def test_select_context_success(mock_run):
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
    server._selected_context = "test-ctx"

    result = await server.call_tool("flux_dryrun", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_kustomize_dryrun_missing_path():
    server._selected_context = "test-ctx"

    result = await server.call_tool("kustomize_dryrun", {})

    assert "path" in result[0].text.lower()
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_kustomize_dryrun_not_a_kustomization(tmp_path):
    server._selected_context = "test-ctx"

    result = await server.call_tool("kustomize_dryrun", {"path": str(tmp_path)})

    assert "not a Kustomize overlay" in result[0].text


@pytest.mark.asyncio
async def test_helm_dryrun_missing_chart_path():
    server._selected_context = "test-ctx"

    result = await server.call_tool("helm_dryrun", {})

    assert "chart_path" in result[0].text
    assert "required" in result[0].text.lower()


@pytest.mark.asyncio
async def test_helm_dryrun_not_a_chart(tmp_path):
    server._selected_context = "test-ctx"

    result = await server.call_tool("helm_dryrun", {"chart_path": str(tmp_path)})

    assert "not a Helm chart" in result[0].text


@pytest.mark.asyncio
async def test_unknown_tool():
    result = await server.call_tool("nonexistent", {})

    assert "Unknown tool" in result[0].text


@pytest.mark.asyncio
async def test_none_arguments():
    result = await server.call_tool("select_kube_context", None)

    assert "required" in result[0].text.lower()


# list_kube_contexts tests


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_list_contexts_no_contexts(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
    ]

    result = await server.call_tool("list_kube_contexts", {})

    assert "no kubectl contexts" in result[0].text.lower()


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_list_contexts_shows_selected(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
    ]
    server._selected_context = "ctx-b"

    result = await server.call_tool("list_kube_contexts", {})

    assert "selected" in result[0].text.lower()
    assert "ctx-b" in result[0].text


# flux_dryrun no files test


@pytest.mark.asyncio
async def test_flux_dryrun_no_yaml_files(tmp_path):
    server._selected_context = "test-ctx"
    (tmp_path / "readme.md").write_text("hello")

    result = await server.call_tool("flux_dryrun", {"path": str(tmp_path)})

    assert "No YAML files" in result[0].text


# list_kube_contexts — additional coverage


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_list_contexts_no_selected_shows_hint(mock_run):
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
@mock.patch("subprocess.run")
async def test_list_contexts_shows_global_current_marker(mock_run):
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_all_pass(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_client_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_server_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_server_pass_with_warnings(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_mixed_results(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_flux_dryrun_shows_context_and_path(mock_run, tmp_path):
    server._selected_context = "prod-cluster"
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
@mock.patch("subprocess.run")
async def test_flux_check_healthy(mock_run):
    server._selected_context = "test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="all checks passed\n", stderr=""
    )

    result = await server.call_tool("flux_check", {})
    text = result[0].text

    assert "HEALTHY" in text
    assert "Context: test-ctx" in text
    assert "all checks passed" in text


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_flux_check_unhealthy(mock_run):
    server._selected_context = "test-ctx"

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="flux-system check failed\n"
    )

    result = await server.call_tool("flux_check", {})
    text = result[0].text

    assert "UNHEALTHY" in text
    assert "Context: test-ctx" in text


# flux_status integration tests


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_flux_status_success(mock_run):
    server._selected_context = "test-ctx"

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
@mock.patch("subprocess.run")
async def test_flux_status_failure(mock_run):
    server._selected_context = "test-ctx"

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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_all_pass(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_build_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_client_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_server_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_server_pass_with_warnings(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kustomize_dryrun_shows_context_and_path(mock_run, tmp_path):
    server._selected_context = "prod-cluster"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_all_pass(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_lint_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_render_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_client_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_server_fail(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_server_pass_with_warnings(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_helm_dryrun_shows_values_and_namespace(mock_run, tmp_path):
    server._selected_context = "test-ctx"
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
@mock.patch("subprocess.run")
async def test_kubeconform_works_without_context(mock_run):
    """Key differentiator: kubeconform does NOT require select_kube_context."""
    server._selected_context = None
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool("kubeconform_validate", {"path": "/tmp/test"})

    assert "Error: No context selected" not in result[0].text
    assert "Kubeconform Schema Validation" in result[0].text


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_kubeconform_all_valid(mock_run):
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
@mock.patch("subprocess.run")
async def test_kubeconform_has_invalid(mock_run):
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
@mock.patch("subprocess.run")
async def test_kubeconform_shows_path(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/my/manifests"},
    )
    text = result[0].text

    assert "Path: /my/manifests" in text


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_kubeconform_shows_kubernetes_version(mock_run):
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
@mock.patch("subprocess.run")
async def test_kubeconform_shows_strict_mode(mock_run):
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
@mock.patch("subprocess.run")
async def test_kubeconform_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("kubeconform")

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "kubeconform not found" in text


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_kubeconform_no_resources(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = await server.call_tool(
        "kubeconform_validate", {"path": "/tmp/test"},
    )
    text = result[0].text

    assert "No resources found" in text


@pytest.mark.asyncio
@mock.patch("subprocess.run")
async def test_kubeconform_shows_error_resources(mock_run):
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
@mock.patch("subprocess.run")
async def test_kubeconform_shows_skipped_resources(mock_run):
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
