import subprocess
from unittest import mock

from kube_lint_mcp.dryrun import (
    build_ctx_args,
    parse_deprecation_warnings,
    kubectl_dry_run,
    KUBECTL_TIMEOUT,
)


# build_ctx_args tests


def test_build_ctx_args_with_context():
    assert build_ctx_args("my-ctx") == ["--context", "my-ctx"]


def test_build_ctx_args_without_context():
    assert build_ctx_args(None) == []


# parse_deprecation_warnings tests


def test_parse_deprecation_warnings_finds_warnings():
    output = (
        "configmap/test configured\n"
        "Warning: policy/v1beta1 PodSecurityPolicy is deprecated\n"
        "Warning: batch/v1beta1 CronJob is deprecated\n"
    )
    result = parse_deprecation_warnings(output)

    assert len(result) == 2
    assert "PodSecurityPolicy is deprecated" in result[0]
    assert "CronJob is deprecated" in result[1]


def test_parse_deprecation_warnings_empty():
    output = "configmap/test configured\nservice/test configured\n"
    result = parse_deprecation_warnings(output)

    assert result == []


# kubectl_dry_run tests


@mock.patch("subprocess.run")
def test_kubectl_dry_run_both_pass(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is True
    assert result.server_passed is True
    assert result.client_error is None
    assert result.server_error is None
    assert result.warnings is None


@mock.patch("subprocess.run")
def test_kubectl_dry_run_client_fail(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid resource"
        ),
    ]

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "invalid resource" in result.client_error


@mock.patch("subprocess.run")
def test_kubectl_dry_run_server_fail(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: forbidden"
        ),
    ]

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is True
    assert result.server_passed is False
    assert "forbidden" in result.server_error


@mock.patch("subprocess.run")
def test_kubectl_dry_run_with_deprecation_warnings(mock_run):
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

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is True
    assert result.server_passed is True
    assert result.warnings is not None
    assert len(result.warnings) == 1
    assert "deprecated" in result.warnings[0].lower()


@mock.patch("subprocess.run")
def test_kubectl_dry_run_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=60)

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "Timeout" in result.client_error


@mock.patch("subprocess.run")
def test_kubectl_dry_run_kubectl_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError("kubectl")

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "kubectl not found" in result.client_error


@mock.patch("subprocess.run")
def test_kubectl_dry_run_passes_context(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    kubectl_dry_run("/tmp/test.yaml", context="my-ctx")

    # Both calls should include --context my-ctx
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        assert "--context" in cmd
        assert "my-ctx" in cmd


@mock.patch("subprocess.run")
def test_kubectl_dry_run_no_context(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    kubectl_dry_run("/tmp/test.yaml", context=None)

    for call in mock_run.call_args_list:
        cmd = call[0][0]
        assert "--context" not in cmd


def test_kubectl_timeout_constant():
    assert KUBECTL_TIMEOUT == 60
