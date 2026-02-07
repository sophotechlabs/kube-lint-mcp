import subprocess

from kube_lint_mcp.dryrun import (
    KUBECTL_TIMEOUT,
    build_ctx_args,
    kubectl_dry_run,
    parse_warnings,
)

# build_ctx_args tests


def test_build_ctx_args_with_context():
    assert build_ctx_args("my-ctx") == ["--context", "my-ctx"]


def test_build_ctx_args_without_context():
    assert build_ctx_args(None) == []


# parse_warnings tests


def test_parse_warnings_finds_deprecation_warnings():
    output = (
        "configmap/test configured\n"
        "Warning: policy/v1beta1 PodSecurityPolicy is deprecated\n"
        "Warning: batch/v1beta1 CronJob is deprecated\n"
    )
    result = parse_warnings(output)

    assert len(result) == 2
    assert "PodSecurityPolicy is deprecated" in result[0]
    assert "CronJob is deprecated" in result[1]


def test_parse_warnings_catches_non_deprecation_warnings():
    output = (
        "configmap/test configured\n"
        "Warning: unknown field spec.foo\n"
    )
    result = parse_warnings(output)

    assert len(result) == 1
    assert "unknown field spec.foo" in result[0]


def test_parse_warnings_empty():
    output = "configmap/test configured\nservice/test configured\n"
    result = parse_warnings(output)

    assert result == []


# kubectl_dry_run tests


def test_kubectl_dry_run_both_pass(mocker):
    mock_run = mocker.patch("subprocess.run")
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


def test_kubectl_dry_run_client_fail(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error: invalid resource"
        ),
    ]

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "invalid resource" in result.client_error


def test_kubectl_dry_run_server_fail(mocker):
    mock_run = mocker.patch("subprocess.run")
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


def test_kubectl_dry_run_with_deprecation_warnings(mocker):
    mock_run = mocker.patch("subprocess.run")
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


def test_kubectl_dry_run_timeout(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=60)

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "Timeout" in result.client_error


def test_kubectl_dry_run_kubectl_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = FileNotFoundError("kubectl")

    result = kubectl_dry_run("/tmp/test.yaml")

    assert result.client_passed is False
    assert result.server_passed is False
    assert "kubectl not found" in result.client_error


def test_kubectl_dry_run_passes_context(mocker):
    mock_run = mocker.patch("subprocess.run")
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


def test_kubectl_dry_run_no_context(mocker):
    mock_run = mocker.patch("subprocess.run")
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


def test_kubectl_dry_run_stdin_data(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    yaml_data = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n"
    result = kubectl_dry_run(stdin_data=yaml_data)

    assert result.client_passed is True
    assert result.server_passed is True
    # Both calls should use -f - for stdin
    for call in mock_run.call_args_list:
        cmd = call[0][0]
        assert "-f" in cmd
        assert "-" in cmd
        assert call[1]["input"] == yaml_data


def test_kubectl_timeout_constant():
    assert KUBECTL_TIMEOUT == 60
