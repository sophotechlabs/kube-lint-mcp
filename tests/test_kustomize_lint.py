import subprocess
from unittest import mock

from kube_lint_mcp import kustomize_lint

# is_kustomization tests


def test_is_kustomization_directory_with_kustomization_yaml(tmp_path):
    (tmp_path / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

    assert kustomize_lint.is_kustomization(str(tmp_path)) is True


def test_is_kustomization_directory_with_kustomization_yml(tmp_path):
    (tmp_path / "kustomization.yml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

    assert kustomize_lint.is_kustomization(str(tmp_path)) is True


def test_is_kustomization_directory_with_uppercase_kustomization(tmp_path):
    (tmp_path / "Kustomization").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

    assert kustomize_lint.is_kustomization(str(tmp_path)) is True


def test_is_kustomization_file_path(tmp_path):
    f = tmp_path / "kustomization.yaml"
    f.write_text("apiVersion: kustomize.config.k8s.io/v1beta1")

    assert kustomize_lint.is_kustomization(str(f)) is True


def test_is_kustomization_false_for_non_kustomization(tmp_path):
    (tmp_path / "deployment.yaml").write_text("apiVersion: apps/v1")

    assert kustomize_lint.is_kustomization(str(tmp_path)) is False


def test_is_kustomization_false_for_nonexistent():
    assert kustomize_lint.is_kustomization("/nonexistent") is False


# validate_kustomization tests


RENDERED_YAML = """\
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


@mock.patch("subprocess.run")
def test_validate_kustomization_all_pass(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1")
    mock_run.side_effect = [
        # kubectl kustomize
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        # client dry-run
        subprocess.CompletedProcess(args=[], returncode=0, stdout="configured", stderr=""),
        # server dry-run
        subprocess.CompletedProcess(args=[], returncode=0, stdout="configured", stderr=""),
    ]

    result = kustomize_lint.validate_kustomization(str(tmp_path), context="my-ctx")

    assert result.build_passed is True
    assert result.client_passed is True
    assert result.server_passed is True
    assert result.resource_count == 2
    assert result.warnings is None


@mock.patch("subprocess.run")
def test_validate_kustomization_passes_context_flag(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    kustomize_lint.validate_kustomization(str(tmp_path), context="prod-cluster")

    # client dry-run call should include --context
    client_args = mock_run.call_args_list[1][0][0]
    assert "--context" in client_args
    assert "prod-cluster" in client_args


@mock.patch("subprocess.run")
def test_validate_kustomization_no_context_flag_when_none(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    kustomize_lint.validate_kustomization(str(tmp_path), context=None)

    client_args = mock_run.call_args_list[1][0][0]
    assert "--context" not in client_args


@mock.patch("subprocess.run")
def test_validate_kustomization_build_fail_stops_early(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: [missing.yaml]")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: missing.yaml not found"
        ),
    ]

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.build_passed is False
    assert result.client_passed is False
    assert result.server_passed is False
    assert "missing.yaml" in result.build_error
    assert mock_run.call_count == 1


@mock.patch("subprocess.run")
def test_validate_kustomization_client_fail(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid manifest"
        ),
    ]

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.build_passed is True
    assert result.client_passed is False
    assert result.server_passed is False
    assert "invalid manifest" in result.client_error


@mock.patch("subprocess.run")
def test_validate_kustomization_server_fail(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: forbidden"
        ),
    ]

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.build_passed is True
    assert result.client_passed is True
    assert result.server_passed is False
    assert "forbidden" in result.server_error


@mock.patch("subprocess.run")
def test_validate_kustomization_server_deprecation_warnings(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="Warning: policy/v1beta1 PodSecurityPolicy is deprecated",
        ),
    ]

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.server_passed is True
    assert result.warnings is not None
    assert any("deprecated" in w.lower() for w in result.warnings)


@mock.patch("subprocess.run")
def test_validate_kustomization_file_path_resolves_to_parent(mock_run, tmp_path):
    f = tmp_path / "kustomization.yaml"
    f.write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    kustomize_lint.validate_kustomization(str(f), context="ctx")

    # kubectl kustomize should receive the directory, not the file
    build_args = mock_run.call_args_list[0][0][0]
    assert build_args[-1] == str(tmp_path)


@mock.patch(
    "subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=60),
)
def test_validate_kustomization_timeout(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.build_passed is False
    assert "Timeout" in result.build_error


@mock.patch("subprocess.run", side_effect=FileNotFoundError)
def test_validate_kustomization_kubectl_not_found(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")

    result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.build_passed is False
    assert "kubectl not found" in result.build_error


@mock.patch("subprocess.run")
def test_validate_kustomization_cleanup_oserror_ignored(mock_run, tmp_path):
    (tmp_path / "kustomization.yaml").write_text("resources: []")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=RENDERED_YAML, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    with mock.patch("os.unlink", side_effect=OSError("permission denied")):
        result = kustomize_lint.validate_kustomization(str(tmp_path))

    assert result.client_passed is True
    assert result.server_passed is True
