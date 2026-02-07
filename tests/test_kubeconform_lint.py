import json
import subprocess

from kube_lint_mcp.kubeconform_lint import (
    KUBECONFORM_TIMEOUT,
    _make_resource,
    _parse_output,
    validate_manifests,
)

# _make_resource tests


def test_make_resource_from_dict():
    r = _make_resource({
        "filename": "deploy.yaml",
        "kind": "Deployment",
        "name": "my-app",
        "version": "apps/v1",
        "status": "statusValid",
        "msg": "",
    })

    assert r.kind == "Deployment"
    assert r.name == "my-app"
    assert r.version == "apps/v1"
    assert r.status == "statusValid"


def test_make_resource_defaults_on_missing_keys():
    r = _make_resource({})

    assert r.filename == ""
    assert r.kind == ""
    assert r.name == ""
    assert r.version == ""
    assert r.status == ""
    assert r.msg == ""


# _parse_output tests


def _make_resource_json(
    status="statusValid", kind="Deployment", name="my-app",
    version="apps/v1", filename="deploy.yaml", msg="",
):
    return json.dumps({
        "filename": filename,
        "kind": kind,
        "name": name,
        "version": version,
        "status": status,
        "msg": msg,
    })


def test_parse_output_jsonl_valid():
    stdout = _make_resource_json() + "\n" + _make_resource_json(
        kind="Service", name="my-svc", version="v1", filename="svc.yaml",
    )
    resources = _parse_output(stdout)

    assert len(resources) == 2
    assert resources[0].kind == "Deployment"
    assert resources[0].status == "statusValid"
    assert resources[1].kind == "Service"


def test_parse_output_wrapped_json():
    data = {
        "resources": [
            {
                "filename": "deploy.yaml",
                "kind": "Deployment",
                "name": "my-app",
                "version": "apps/v1",
                "status": "statusValid",
                "msg": "",
            },
        ]
    }
    resources = _parse_output(json.dumps(data))

    assert len(resources) == 1
    assert resources[0].kind == "Deployment"


def test_parse_output_empty():
    assert _parse_output("") == []
    assert _parse_output("  \n  ") == []


def test_parse_output_malformed_json():
    resources = _parse_output("this is not json\nalso not json")

    assert resources == []


def test_parse_output_skips_blank_lines_in_jsonl():
    stdout = _make_resource_json() + "\n\n" + _make_resource_json(
        kind="Service", name="svc",
    )
    resources = _parse_output(stdout)

    assert len(resources) == 2


def test_parse_output_mixed_valid_and_garbage():
    stdout = _make_resource_json() + "\nnot json\n" + _make_resource_json(
        kind="Service", name="svc",
    )
    resources = _parse_output(stdout)

    assert len(resources) == 2


# validate_manifests tests


def test_validate_all_valid(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = "\n".join([
        _make_resource_json(),
        _make_resource_json(kind="Service", name="my-svc", version="v1"),
    ])
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr="",
    )

    result = validate_manifests("/tmp/manifests")

    assert result.passed is True
    assert result.valid == 2
    assert result.invalid == 0
    assert result.errors == 0
    assert result.skipped == 0
    assert result.error is None
    assert len(result.resources) == 2


def test_validate_has_invalid(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = "\n".join([
        _make_resource_json(),
        _make_resource_json(
            status="statusInvalid", kind="Deployment", name="bad",
            msg="spec.replicas: Invalid type",
        ),
    ])
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=stdout, stderr="",
    )

    result = validate_manifests("/tmp/manifests")

    assert result.passed is False
    assert result.valid == 1
    assert result.invalid == 1


def test_validate_has_errors(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = _make_resource_json(
        status="statusError", msg="could not download schema",
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=stdout, stderr="",
    )

    result = validate_manifests("/tmp/manifests")

    assert result.passed is False
    assert result.errors == 1


def test_validate_skipped_only(mocker):
    mock_run = mocker.patch("subprocess.run")
    stdout = _make_resource_json(status="statusSkipped", kind="MyCRD", name="x")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr="",
    )

    result = validate_manifests("/tmp/manifests")

    assert result.passed is True
    assert result.skipped == 1
    assert result.valid == 0


def test_validate_empty_output(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    result = validate_manifests("/tmp/manifests")

    assert result.passed is True
    assert result.resources == []
    assert result.valid == 0


def test_validate_timeout(mocker):
    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kubeconform", timeout=120))

    result = validate_manifests("/tmp/manifests")

    assert result.passed is False
    assert "Timeout" in result.error


def test_validate_not_found(mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("kubeconform"))

    result = validate_manifests("/tmp/manifests")

    assert result.passed is False
    assert "kubeconform not found" in result.error


def test_validate_kubernetes_version_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/manifests", kubernetes_version="1.29.0")

    cmd = mock_run.call_args[0][0]
    assert "-kubernetes-version" in cmd
    assert "1.29.0" in cmd


def test_validate_master_version_omits_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/manifests", kubernetes_version="master")

    cmd = mock_run.call_args[0][0]
    assert "-kubernetes-version" not in cmd


def test_validate_strict_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/manifests", strict=True)

    cmd = mock_run.call_args[0][0]
    assert "-strict" in cmd


def test_validate_strict_false_omits_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/manifests", strict=False)

    cmd = mock_run.call_args[0][0]
    assert "-strict" not in cmd


def test_validate_default_flags_always_present(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/manifests")

    cmd = mock_run.call_args[0][0]
    assert "-ignore-missing-schemas" in cmd
    assert "-output" in cmd
    assert "json" in cmd
    assert "-summary" in cmd


def test_validate_path_in_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr="",
    )

    validate_manifests("/tmp/my-manifests")

    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == "/tmp/my-manifests"


def test_timeout_constant():
    assert KUBECONFORM_TIMEOUT == 120
