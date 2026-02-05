import subprocess
from unittest import mock

from kube_lint_mcp import flux_lint

# find_yaml_files tests


def test_find_yaml_files_single_yaml(tmp_path):
    f = tmp_path / "manifest.yaml"
    f.write_text("apiVersion: v1")

    result = flux_lint.find_yaml_files(str(f))

    assert result == [str(f)]


def test_find_yaml_files_single_yml(tmp_path):
    f = tmp_path / "manifest.yml"
    f.write_text("apiVersion: v1")

    result = flux_lint.find_yaml_files(str(f))

    assert result == [str(f)]


def test_find_yaml_files_ignores_non_yaml(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("hello")

    result = flux_lint.find_yaml_files(str(f))

    assert result == []


def test_find_yaml_files_recursively_in_directory(tmp_path):
    (tmp_path / "a.yaml").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.yml").write_text("b")

    result = flux_lint.find_yaml_files(str(tmp_path))

    assert len(result) == 2
    assert all(f.endswith((".yaml", ".yml")) for f in result)


def test_find_yaml_files_returns_sorted(tmp_path):
    (tmp_path / "z.yaml").write_text("z")
    (tmp_path / "a.yaml").write_text("a")

    result = flux_lint.find_yaml_files(str(tmp_path))

    assert result == sorted(result)


def test_find_yaml_files_nonexistent_path():
    result = flux_lint.find_yaml_files("/nonexistent/path")

    assert result == []


# get_kubectl_contexts tests


@mock.patch("subprocess.run")
def test_get_kubectl_contexts_returns_contexts_and_current(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
    ]

    contexts, current = flux_lint.get_kubectl_contexts()

    assert contexts == ["ctx-a", "ctx-b"]
    assert current == "ctx-a"


@mock.patch("subprocess.run")
def test_get_kubectl_contexts_no_current(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error"),
    ]

    contexts, current = flux_lint.get_kubectl_contexts()

    assert contexts == ["ctx-a"]
    assert current is None


@mock.patch(
    "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=10)
)
def test_get_kubectl_contexts_timeout(mock_run):
    contexts, current = flux_lint.get_kubectl_contexts()

    assert contexts == []
    assert current is None


@mock.patch("subprocess.run", side_effect=FileNotFoundError)
def test_get_kubectl_contexts_kubectl_not_found(mock_run):
    contexts, current = flux_lint.get_kubectl_contexts()

    assert contexts == []
    assert current is None


# context_exists tests


@mock.patch("subprocess.run")
def test_context_exists_true(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="my-ctx\nother\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="my-ctx\n", stderr=""
        ),
    ]

    assert flux_lint.context_exists("my-ctx") is True


@mock.patch("subprocess.run")
def test_context_exists_false(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ctx-a\nctx-b\n", stderr=""
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ctx-a\n", stderr=""),
    ]

    assert flux_lint.context_exists("nonexistent") is False


# validate_manifest tests


@mock.patch("subprocess.run")
def test_validate_manifest_both_pass(mock_run, tmp_path):
    f = tmp_path / "good.yaml"
    f.write_text("apiVersion: v1\nkind: ConfigMap")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="configured\n", stderr=""
        ),
    ]

    result = flux_lint.validate_manifest(str(f), context="my-ctx")

    assert result.client_passed is True
    assert result.server_passed is True
    assert result.warnings is None


@mock.patch("subprocess.run")
def test_validate_manifest_passes_context_flag(mock_run, tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text("apiVersion: v1")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    flux_lint.validate_manifest(str(f), context="prod-cluster")

    first_call_args = mock_run.call_args_list[0][0][0]
    assert "--context" in first_call_args
    assert "prod-cluster" in first_call_args


@mock.patch("subprocess.run")
def test_validate_manifest_no_context_flag_when_none(mock_run, tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text("apiVersion: v1")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    flux_lint.validate_manifest(str(f), context=None)

    first_call_args = mock_run.call_args_list[0][0][0]
    assert "--context" not in first_call_args


@mock.patch("subprocess.run")
def test_validate_manifest_client_fail(mock_run, tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("invalid")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="error: invalid manifest"
    )

    result = flux_lint.validate_manifest(str(f))

    assert result.client_passed is False
    assert result.server_passed is False
    assert "invalid manifest" in result.client_error


@mock.patch("subprocess.run")
def test_validate_manifest_server_fail(mock_run, tmp_path):
    f = tmp_path / "srvfail.yaml"
    f.write_text("apiVersion: v1")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="server rejected"
        ),
    ]

    result = flux_lint.validate_manifest(str(f))

    assert result.client_passed is True
    assert result.server_passed is False
    assert "server rejected" in result.server_error


@mock.patch("subprocess.run")
def test_validate_manifest_captures_deprecation_warnings(mock_run, tmp_path):
    f = tmp_path / "dep.yaml"
    f.write_text("apiVersion: v1")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="Warning: v1beta1 is deprecated, use v1",
        ),
    ]

    result = flux_lint.validate_manifest(str(f))

    assert result.server_passed is True
    assert result.warnings is not None
    assert any("deprecated" in w.lower() for w in result.warnings)


@mock.patch(
    "subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=30),
)
def test_validate_manifest_timeout(mock_run, tmp_path):
    f = tmp_path / "slow.yaml"
    f.write_text("apiVersion: v1")

    result = flux_lint.validate_manifest(str(f))

    assert result.client_passed is False
    assert "Timeout" in result.client_error


@mock.patch("subprocess.run", side_effect=FileNotFoundError)
def test_validate_manifest_kubectl_not_found(mock_run, tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text("apiVersion: v1")

    result = flux_lint.validate_manifest(str(f))

    assert result.client_passed is False
    assert "kubectl not found" in result.client_error


# validate_manifests tests


@mock.patch("subprocess.run")
def test_validate_manifests_validates_all_files(mock_run, tmp_path):
    (tmp_path / "a.yaml").write_text("a")
    (tmp_path / "b.yaml").write_text("b")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="ok", stderr=""
    )

    results = flux_lint.validate_manifests(str(tmp_path))

    assert len(results) == 2


def test_validate_manifests_empty_for_no_yaml(tmp_path):
    (tmp_path / "readme.md").write_text("hello")

    results = flux_lint.validate_manifests(str(tmp_path))

    assert results == []


# run_flux_check tests


@mock.patch("subprocess.run")
def test_run_flux_check_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="all checks passed\n", stderr=""
    )

    success, output = flux_lint.run_flux_check(context="my-ctx")

    assert success is True
    assert "all checks passed" in output


@mock.patch("subprocess.run")
def test_run_flux_check_passes_context(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="ok", stderr=""
    )

    flux_lint.run_flux_check(context="prod")

    call_args = mock_run.call_args[0][0]
    assert "--context" in call_args
    assert "prod" in call_args


@mock.patch("subprocess.run")
def test_run_flux_check_failure(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="component unhealthy"
    )

    success, output = flux_lint.run_flux_check()

    assert success is False
    assert "unhealthy" in output


@mock.patch(
    "subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="flux", timeout=60),
)
def test_run_flux_check_timeout(mock_run):
    success, output = flux_lint.run_flux_check()

    assert success is False
    assert "Timeout" in output


@mock.patch("subprocess.run", side_effect=FileNotFoundError)
def test_run_flux_check_flux_not_found(mock_run):
    success, output = flux_lint.run_flux_check()

    assert success is False
    assert "not found" in output


# get_flux_status tests


@mock.patch("subprocess.run")
def test_get_flux_status_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="NAME\tREADY\nmy-app\tTrue\n",
        stderr="",
    )

    success, output = flux_lint.get_flux_status(context="my-ctx")

    assert success is True
    assert "my-app" in output


@mock.patch("subprocess.run")
def test_get_flux_status_failure(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="connection refused"
    )

    success, output = flux_lint.get_flux_status()

    assert success is False
    assert "connection refused" in output


@mock.patch(
    "subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="flux", timeout=60),
)
def test_get_flux_status_timeout(mock_run):
    success, output = flux_lint.get_flux_status()

    assert success is False
    assert "Timeout" in output


@mock.patch("subprocess.run", side_effect=FileNotFoundError)
def test_get_flux_status_flux_not_found(mock_run):
    success, output = flux_lint.get_flux_status()

    assert success is False
    assert "not found" in output
