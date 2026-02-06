import subprocess
from unittest import mock

from kube_lint_mcp import helm_lint

# is_helm_chart tests


def test_is_helm_chart_directory_with_chart_yaml(tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: my-chart")

    assert helm_lint.is_helm_chart(str(tmp_path)) is True


def test_is_helm_chart_directory_with_lowercase(tmp_path):
    (tmp_path / "chart.yaml").write_text("name: my-chart")

    assert helm_lint.is_helm_chart(str(tmp_path)) is True


def test_is_helm_chart_file_in_chart_dir(tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: my-chart")
    values = tmp_path / "values.yaml"
    values.write_text("key: val")

    assert helm_lint.is_helm_chart(str(values)) is True


def test_is_helm_chart_false_for_non_chart(tmp_path):
    (tmp_path / "random.yaml").write_text("data")

    assert helm_lint.is_helm_chart(str(tmp_path)) is False


def test_is_helm_chart_false_for_nonexistent():
    assert helm_lint.is_helm_chart("/nonexistent") is False


# validate_helm_chart tests


@mock.patch("subprocess.run")
def test_validate_helm_chart_all_pass(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n"
    mock_run.side_effect = [
        # lint
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        # template
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        # client dry-run
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        # server dry-run
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path), context="my-ctx")

    assert result.lint_passed is True
    assert result.render_passed is True
    assert result.client_passed is True
    assert result.server_passed is True
    assert result.resource_count == 1


@mock.patch("subprocess.run")
def test_validate_helm_chart_lint_fail(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="lint error"
        ),
        # template still runs
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n",
            stderr="",
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is False
    assert "lint error" in result.lint_error


@mock.patch("subprocess.run")
def test_validate_helm_chart_render_fail_stops_early(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="render error"
        ),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.render_passed is False
    assert result.client_passed is False
    assert result.server_passed is False


@mock.patch("subprocess.run")
def test_validate_helm_chart_client_fail(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n"
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="client reject"
        ),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.render_passed is True
    assert result.client_passed is False
    assert result.server_passed is False


@mock.patch("subprocess.run")
def test_validate_helm_chart_server_deprecation_warnings(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n"
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="Warning: apps/v1beta1 is deprecated",
        ),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.server_passed is True
    assert result.warnings is not None
    assert any("deprecated" in w.lower() for w in result.warnings)


@mock.patch("subprocess.run")
def test_validate_helm_chart_passes_values_and_namespace(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    values = tmp_path / "values.yaml"
    values.write_text("key: val")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n"
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    helm_lint.validate_helm_chart(
        str(tmp_path),
        values_file=str(values),
        namespace="prod",
        release_name="my-release",
    )

    # helm lint call should include -f values
    lint_args = mock_run.call_args_list[0][0][0]
    assert "-f" in lint_args
    assert str(values) in lint_args

    # helm template call should include namespace and release name
    template_args = mock_run.call_args_list[1][0][0]
    assert "--namespace" in template_args
    assert "prod" in template_args
    assert "my-release" in template_args


def test_validate_helm_chart_not_a_chart(tmp_path):
    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is False
    assert "missing Chart.yaml" in result.lint_error


@mock.patch(
    "subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="helm", timeout=60),
)
def test_validate_helm_chart_timeout(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is False
    assert "Timeout" in result.lint_error


# validate_helm_chart edge cases for full coverage


@mock.patch("subprocess.run")
def test_validate_helm_chart_cleanup_oserror_ignored(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n"
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    ]

    with mock.patch("os.unlink", side_effect=OSError("permission denied")):
        result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.client_passed is True
    assert result.server_passed is True


@mock.patch("subprocess.run", side_effect=FileNotFoundError("helm"))
def test_validate_helm_chart_helm_not_found(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is False
    assert "helm not found" in result.lint_error


@mock.patch("subprocess.run")
def test_validate_helm_chart_kubectl_not_found(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    rendered = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: t\n"
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=rendered, stderr=""),
        FileNotFoundError("No such file or directory: 'kubectl'"),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is True
    assert result.render_passed is True
    assert result.client_passed is False
    assert "kubectl not found" in result.client_error


@mock.patch("subprocess.run")
def test_validate_helm_chart_malformed_rendered_yaml(mock_run, tmp_path):
    (tmp_path / "Chart.yaml").write_text("name: test")
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="{{{bad yaml", stderr=""),
    ]

    result = helm_lint.validate_helm_chart(str(tmp_path))

    assert result.lint_passed is True
    assert result.render_passed is True
    assert result.client_passed is False
    assert "Failed to parse rendered YAML" in result.render_error
