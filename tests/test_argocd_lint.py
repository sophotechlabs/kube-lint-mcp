import json
import os
import subprocess

from kube_lint_mcp import argocd_lint

# Simulates successful namespace auto-detection (kubectl get configmap argocd-cm)
_DETECT_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="argocd", stderr="")
_DETECT_FAIL = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not found")

# kubectl set-context succeeds (used by _build_temp_kubeconfig)
_SET_CTX_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="Context modified.", stderr="")

# JSON fixtures — kubectl wraps items in {"apiVersion":..., "items": [...]}

_APP_ITEMS = [
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
    {
        "metadata": {"name": "other-app", "namespace": "argocd"},
        "spec": {
            "project": "default",
            "source": {
                "repoURL": "https://github.com/org/repo.git",
                "path": "k8s/other",
                "targetRevision": "main",
            },
        },
        "status": {
            "sync": {"status": "OutOfSync"},
            "health": {"status": "Degraded"},
        },
    },
]

KUBECTL_APP_LIST_JSON = json.dumps({
    "apiVersion": "argoproj.io/v1alpha1",
    "kind": "ApplicationList",
    "items": _APP_ITEMS,
})

KUBECTL_APP_GET_JSON = json.dumps({
    "apiVersion": "argoproj.io/v1alpha1",
    "kind": "Application",
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
        "health": {"status": "Healthy", "message": ""},
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
            {
                "kind": "Service",
                "namespace": "default",
                "name": "my-app-svc",
                "status": "Synced",
                "health": {"status": "Healthy"},
            },
        ],
    },
})

KUBECTL_APP_GET_MINIMAL_JSON = json.dumps({
    "apiVersion": "argoproj.io/v1alpha1",
    "kind": "Application",
    "metadata": {"name": "simple-app", "namespace": "argocd"},
    "spec": {
        "project": "default",
        "source": {
            "repoURL": "https://github.com/org/repo.git",
            "path": ".",
            "targetRevision": "HEAD",
        },
    },
    "status": {
        "sync": {"status": "Synced"},
        "health": {"status": "Healthy"},
    },
})

ARGOCD_DIFF_OUTPUT = """\
===== apps/Deployment default/my-app ======
  10,11c10,11
<   replicas: 2
>   replicas: 3
"""


# _detect_argocd_namespace tests


def test_detect_namespace_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="argocd", stderr=""
    )

    result = argocd_lint._detect_argocd_namespace("my-ctx")

    assert result == "argocd"
    cmd = mock_run.call_args[0][0]
    assert "kubectl" in cmd
    assert "--all-namespaces" in cmd
    assert "--context" in cmd
    assert "my-ctx" in cmd


def test_detect_namespace_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="not found"
    )

    result = argocd_lint._detect_argocd_namespace("my-ctx")

    assert result is None


def test_detect_namespace_empty_output(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    result = argocd_lint._detect_argocd_namespace("my-ctx")

    assert result is None


def test_detect_namespace_timeout(mocker):
    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=30))
    result = argocd_lint._detect_argocd_namespace("my-ctx")

    assert result is None


def test_detect_namespace_kubectl_not_found(mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("kubectl"))
    result = argocd_lint._detect_argocd_namespace("my-ctx")

    assert result is None


# auto-detect integration: list_argocd_apps calls detect when no namespace


def test_list_apps_auto_detects_namespace(mocker):
    """Should auto-detect namespace then use it in kubectl -n flag."""
    mock_run = mocker.patch("subprocess.run")
    kubectl_empty = json.dumps({"apiVersion": "argoproj.io/v1alpha1", "items": []})
    mock_run.side_effect = [
        # First call: _detect_argocd_namespace (kubectl get configmap)
        subprocess.CompletedProcess(args=[], returncode=0, stdout="argo-cd", stderr=""),
        # Second call: kubectl get applications
        subprocess.CompletedProcess(args=[], returncode=0, stdout=kubectl_empty, stderr=""),
    ]

    argocd_lint.list_argocd_apps(context="my-ctx")

    kubectl_cmd = mock_run.call_args_list[1][0][0]
    assert "kubectl" in kubectl_cmd
    assert "-n" in kubectl_cmd
    assert "argo-cd" in kubectl_cmd


def test_list_apps_skips_detect_when_namespace_provided(mocker):
    """Should skip auto-detection when namespace is explicitly provided."""
    mock_run = mocker.patch("subprocess.run")
    kubectl_empty = json.dumps({"apiVersion": "argoproj.io/v1alpha1", "items": []})
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=kubectl_empty, stderr=""
    )

    argocd_lint.list_argocd_apps(context="my-ctx", namespace="custom-ns")

    # Only one call (no detection)
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    assert "-n" in cmd
    assert "custom-ns" in cmd


def test_list_apps_errors_when_namespace_not_detected(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = _DETECT_FAIL

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "auto-detect" in (result.error or "").lower()


def test_get_app_errors_when_namespace_not_detected(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = _DETECT_FAIL

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "auto-detect" in (result.error or "").lower()


def test_diff_app_errors_when_namespace_not_detected(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = _DETECT_FAIL

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "auto-detect" in (result.error or "").lower()


# _build_argocd_args tests


def test_build_args_with_context():
    """Should return --core --kube-context CTX."""
    args = argocd_lint._build_argocd_args("my-ctx")

    assert args == ["--core", "--kube-context", "my-ctx"]


# _build_temp_kubeconfig tests


def test_build_temp_kubeconfig_creates_copy(mocker, tmp_path):
    """Should copy kubeconfig and set namespace on context."""
    fake_kubeconfig = tmp_path / "config"
    fake_kubeconfig.write_text("apiVersion: v1\n")
    mocker.patch.dict(os.environ, {"KUBECONFIG": str(fake_kubeconfig)})

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = _SET_CTX_OK

    result = argocd_lint._build_temp_kubeconfig("my-ctx", "argo-cd")

    try:
        assert os.path.exists(result)
        assert result.endswith(".kubeconfig")
        # Verify kubectl config set-context was called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "kubectl"
        assert "config" in cmd
        assert "set-context" in cmd
        assert "my-ctx" in cmd
        assert "--namespace" in cmd
        assert "argo-cd" in cmd
        assert "--kubeconfig" in cmd
        assert result in cmd
    finally:
        if os.path.exists(result):
            os.unlink(result)


def test_build_temp_kubeconfig_uses_default_path(mocker, tmp_path):
    """Should fall back to ~/.kube/config when KUBECONFIG is not set."""
    fake_home_config = tmp_path / "config"
    fake_home_config.write_text("apiVersion: v1\n")
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch("os.path.expanduser", return_value=str(fake_home_config))

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = _SET_CTX_OK

    result = argocd_lint._build_temp_kubeconfig("my-ctx", "argocd")

    try:
        assert os.path.exists(result)
    finally:
        if os.path.exists(result):
            os.unlink(result)


# list_argocd_apps tests


def test_list_apps_success(mocker):
    """Should parse kubectl ApplicationList items."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=KUBECTL_APP_LIST_JSON, stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 2
    assert result.apps[0].name == "my-app"
    assert result.apps[0].sync_status == "Synced"
    assert result.apps[0].health_status == "Healthy"
    assert result.apps[0].repo_url == "https://github.com/org/repo.git"
    assert result.apps[1].name == "other-app"
    assert result.apps[1].sync_status == "OutOfSync"
    assert result.apps[1].health_status == "Degraded"


def test_list_apps_empty(mocker):
    """Should handle empty items list."""
    mock_run = mocker.patch("subprocess.run")
    kubectl_empty = json.dumps({"apiVersion": "argoproj.io/v1alpha1", "items": []})
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=kubectl_empty, stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


def test_list_apps_uses_kubectl(mocker):
    """Should use kubectl get applications.argoproj.io."""
    mock_run = mocker.patch("subprocess.run")
    kubectl_empty = json.dumps({"apiVersion": "argoproj.io/v1alpha1", "items": []})
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=kubectl_empty, stderr=""),
    ]

    argocd_lint.list_argocd_apps(context="prod-cluster")

    cmd = mock_run.call_args_list[1][0][0]
    assert cmd[0] == "kubectl"
    assert "get" in cmd
    assert "applications.argoproj.io" in cmd
    assert "--context" in cmd
    assert "prod-cluster" in cmd


def test_list_apps_passes_namespace(mocker):
    """Should pass namespace via -n flag to kubectl."""
    mock_run = mocker.patch("subprocess.run")
    kubectl_empty = json.dumps({"apiVersion": "argoproj.io/v1alpha1", "items": []})
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=kubectl_empty, stderr=""
    )

    argocd_lint.list_argocd_apps(context="my-ctx", namespace="argo-cd")

    cmd = mock_run.call_args[0][0]
    assert "-n" in cmd
    assert "argo-cd" in cmd


def test_list_apps_command_failure(mocker):
    """Should return error on non-zero exit."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error from server"),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "error" in (result.error or "").lower()


def test_list_apps_kubectl_not_found(mocker):
    """Should return error when kubectl is not on PATH."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        FileNotFoundError("kubectl"),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_list_apps_timeout(mocker):
    """Should return error on timeout."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.TimeoutExpired(cmd="kubectl", timeout=60),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "Timeout" in (result.error or "")


def test_list_apps_json_parse_error(mocker):
    """Should return error on malformed JSON."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "parse" in (result.error or "").lower()


# get_argocd_app tests


def test_get_app_success(mocker):
    """Should parse kubectl Application object."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=KUBECTL_APP_GET_JSON, stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.name == "my-app"
    assert result.project == "default"
    assert result.sync_status == "Synced"
    assert result.health_status == "Healthy"
    assert result.repo_url == "https://github.com/org/repo.git"


def test_get_app_with_resources_and_conditions(mocker):
    """Should extract resources and conditions."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=KUBECTL_APP_GET_JSON, stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.resources is not None
    assert len(result.resources) == 2
    assert result.resources[0]["kind"] == "Deployment"
    assert result.resources[0]["health"] == "Healthy"
    assert result.conditions is not None
    assert len(result.conditions) == 1
    assert "SyncError" in result.conditions[0]


def test_get_app_minimal(mocker):
    """Should handle app with no resources or conditions."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=KUBECTL_APP_GET_MINIMAL_JSON, stderr=""),
    ]

    result = argocd_lint.get_argocd_app("simple-app", context="my-ctx")

    assert result.success is True
    assert result.name == "simple-app"
    assert result.resources is None
    assert result.conditions is None


def test_get_app_uses_kubectl(mocker):
    """Should use kubectl get applications.argoproj.io/<name>."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=KUBECTL_APP_GET_MINIMAL_JSON, stderr=""),
    ]

    argocd_lint.get_argocd_app("my-app", context="prod-cluster")

    cmd = mock_run.call_args_list[1][0][0]
    assert cmd[0] == "kubectl"
    assert "get" in cmd
    assert "applications.argoproj.io/my-app" in cmd
    assert "--context" in cmd
    assert "prod-cluster" in cmd


def test_get_app_passes_namespace(mocker):
    """Should pass namespace via -n flag to kubectl."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=KUBECTL_APP_GET_MINIMAL_JSON, stderr=""
    )

    argocd_lint.get_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    cmd = mock_run.call_args[0][0]
    assert "-n" in cmd
    assert "argo-cd" in cmd


def test_get_app_command_failure(mocker):
    """Should return error on non-zero exit."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="app 'missing' not found"),
    ]

    result = argocd_lint.get_argocd_app("missing", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_get_app_kubectl_not_found(mocker):
    """Should return error when kubectl is not on PATH."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        FileNotFoundError("kubectl"),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_get_app_timeout(mocker):
    """Should return error on timeout."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.TimeoutExpired(cmd="kubectl", timeout=60),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "Timeout" in (result.error or "")


def test_get_app_json_parse_error(mocker):
    """Should return error on malformed JSON."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "parse" in (result.error or "").lower()


def test_get_app_unexpected_format(mocker):
    """Should return error when response is not a dict."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout='"just a string"', stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "Unexpected" in (result.error or "")


# diff_argocd_app tests


def _mock_diff_setup(mocker, tmp_path):
    """Set up mocks for diff tests: temp kubeconfig + subprocess."""
    fake_kubeconfig = tmp_path / "config"
    fake_kubeconfig.write_text("apiVersion: v1\n")
    mocker.patch.dict(os.environ, {"KUBECONFIG": str(fake_kubeconfig)})
    mock_run = mocker.patch("subprocess.run")
    return mock_run


def test_diff_app_in_sync(mocker, tmp_path):
    """Should return in_sync=True when argocd diff exits 0."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _DETECT_OK,
        _SET_CTX_OK,  # _build_temp_kubeconfig
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.in_sync is True
    assert result.diff_output == ""


def test_diff_app_has_diff(mocker, tmp_path):
    """Should return diff output when argocd diff exits 1."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _DETECT_OK,
        _SET_CTX_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout=ARGOCD_DIFF_OUTPUT, stderr=""),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.in_sync is False
    assert "replicas" in result.diff_output


def test_diff_app_error(mocker, tmp_path):
    """Should return error when argocd diff exits 2."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _DETECT_OK,
        _SET_CTX_OK,
        subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="FATA[0000] app not found"),
    ]

    result = argocd_lint.diff_argocd_app("missing", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_diff_app_uses_temp_kubeconfig(mocker, tmp_path):
    """Should pass KUBECONFIG env var pointing to temp file."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _SET_CTX_OK,  # _build_temp_kubeconfig (no detect — namespace provided)
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    argocd_lint.diff_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    # Second call is the argocd diff command
    diff_call = mock_run.call_args_list[1]
    diff_kwargs = diff_call[1] if diff_call[1] else {}
    env = diff_kwargs.get("env", {})
    assert "KUBECONFIG" in env
    assert env["KUBECONFIG"].endswith(".kubeconfig")


def test_diff_app_no_namespace_flag(mocker, tmp_path):
    """Should NOT pass --namespace flag to argocd CLI."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _SET_CTX_OK,  # _build_temp_kubeconfig (no detect — namespace provided)
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    argocd_lint.diff_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    # Second call is the argocd diff command
    cmd = mock_run.call_args_list[1][0][0]
    assert "--namespace" not in cmd
    assert "--core" in cmd
    assert "--kube-context" in cmd
    assert "my-ctx" in cmd
    assert "my-app" in cmd


def test_diff_app_cleans_up_temp_file(mocker, tmp_path):
    """Should delete temp kubeconfig even on success."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _SET_CTX_OK,  # _build_temp_kubeconfig
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    argocd_lint.diff_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    # Second call was set-context, which received --kubeconfig <path>
    set_ctx_cmd = mock_run.call_args_list[0][0][0]
    kubeconfig_idx = set_ctx_cmd.index("--kubeconfig")
    temp_path = set_ctx_cmd[kubeconfig_idx + 1]
    assert not os.path.exists(temp_path)


def test_diff_app_argocd_not_found(mocker, tmp_path):
    """Should return error when argocd CLI is not on PATH."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _DETECT_OK,
        _SET_CTX_OK,
        FileNotFoundError("argocd"),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_diff_app_timeout(mocker, tmp_path):
    """Should return error on timeout."""
    mock_run = _mock_diff_setup(mocker, tmp_path)
    mock_run.side_effect = [
        _DETECT_OK,
        _SET_CTX_OK,
        subprocess.TimeoutExpired(cmd="argocd", timeout=60),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "Timeout" in (result.error or "")


# _extract_source tests


def test_extract_source_from_source():
    spec = {"source": {"repoURL": "https://git.example.com", "path": "k8s", "targetRevision": "main"}}
    url, path, rev = argocd_lint._extract_source(spec)
    assert url == "https://git.example.com"
    assert path == "k8s"
    assert rev == "main"


def test_extract_source_from_sources():
    spec = {"sources": [{"repoURL": "https://git.example.com", "path": "app", "targetRevision": "v1"}]}
    url, path, rev = argocd_lint._extract_source(spec)
    assert url == "https://git.example.com"
    assert path == "app"
    assert rev == "v1"


def test_extract_source_empty():
    url, path, rev = argocd_lint._extract_source({})
    assert url == ""
    assert path == ""
    assert rev == ""


def test_extract_source_non_dict_source():
    url, path, rev = argocd_lint._extract_source({"source": "not a dict"})
    assert url == ""
    assert path == ""
    assert rev == ""


# Edge case: non-dict items in kubectl response


def test_list_apps_no_items_key(mocker):
    """Should handle kubectl response without items key."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout='{"not": "items"}', stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


def test_list_apps_non_dict_items(mocker):
    """Should skip non-dict items in the items array."""
    mock_run = mocker.patch("subprocess.run")
    data = json.dumps({"items": ["not a dict", 42]})
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=data, stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


# Edge case: non-dict resource in get_app


def test_get_app_with_non_dict_resource(mocker):
    """Should skip non-dict entries in resources array."""
    mock_run = mocker.patch("subprocess.run")
    data = {
        "metadata": {"name": "app", "namespace": "argocd"},
        "spec": {"project": "default", "source": {"repoURL": "", "path": "", "targetRevision": ""}},
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
            "resources": [
                "not a dict",
                {
                    "kind": "Service", "name": "svc", "namespace": "default",
                    "status": "Synced", "health": {"status": "Healthy"},
                },
            ],
        },
    }
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(data), stderr=""),
    ]

    result = argocd_lint.get_argocd_app("app", context="my-ctx")

    assert result.success is True
    assert result.resources is not None
    assert len(result.resources) == 1
    assert result.resources[0]["kind"] == "Service"
