import json
import subprocess

from kube_lint_mcp import argocd_lint

# Simulates successful namespace auto-detection (kubectl get configmap argocd-cm)
_DETECT_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="argocd", stderr="")
_DETECT_FAIL = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not found")

# JSON fixtures

ARGOCD_APP_LIST_JSON = json.dumps([
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
])

ARGOCD_APP_GET_JSON = json.dumps({
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

ARGOCD_APP_GET_MINIMAL_JSON = json.dumps({
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
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        # First call: _detect_argocd_namespace (kubectl)
        subprocess.CompletedProcess(args=[], returncode=0, stdout="argo-cd", stderr=""),
        # Second call: argocd app list
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    argocd_lint.list_argocd_apps(context="my-ctx")

    # Second call should have --namespace argo-cd
    argocd_cmd = mock_run.call_args_list[1][0][0]
    assert "--namespace" in argocd_cmd
    assert "argo-cd" in argocd_cmd


def test_list_apps_skips_detect_when_namespace_provided(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="[]", stderr=""
    )

    argocd_lint.list_argocd_apps(context="my-ctx", namespace="custom-ns")

    # Only one call (no detection)
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    assert "--namespace" in cmd
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


def test_build_args_with_context_only():
    args = argocd_lint._build_argocd_args("my-ctx")

    assert args == ["--core", "--kube-context", "my-ctx"]


def test_build_args_with_context_and_namespace():
    args = argocd_lint._build_argocd_args("my-ctx", namespace="argocd")

    assert args == ["--core", "--kube-context", "my-ctx", "--namespace", "argocd"]


def test_build_args_with_none_namespace():
    args = argocd_lint._build_argocd_args("my-ctx", namespace=None)

    assert args == ["--core", "--kube-context", "my-ctx"]


def test_build_args_with_empty_namespace():
    args = argocd_lint._build_argocd_args("my-ctx", namespace="")

    assert args == ["--core", "--kube-context", "my-ctx"]


# list_argocd_apps tests


def test_list_apps_success(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_APP_LIST_JSON, stderr=""),
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
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


def test_list_apps_passes_kube_context_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    argocd_lint.list_argocd_apps(context="prod-cluster")

    cmd = mock_run.call_args_list[1][0][0]
    assert "--core" in cmd
    assert "--kube-context" in cmd
    assert "prod-cluster" in cmd


def test_list_apps_passes_namespace_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="[]", stderr=""
    )

    argocd_lint.list_argocd_apps(context="my-ctx", namespace="argo-cd")

    cmd = mock_run.call_args[0][0]
    assert "--namespace" in cmd
    assert "argo-cd" in cmd


def test_list_apps_command_failure(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="FATA[0000] some error"),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "some error" in (result.error or "")


def test_list_apps_argocd_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        FileNotFoundError("argocd"),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_list_apps_timeout(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.TimeoutExpired(cmd="argocd", timeout=60),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is False
    assert "Timeout" in (result.error or "")


def test_list_apps_json_parse_error(mocker):
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
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_APP_GET_JSON, stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.name == "my-app"
    assert result.project == "default"
    assert result.sync_status == "Synced"
    assert result.health_status == "Healthy"
    assert result.repo_url == "https://github.com/org/repo.git"


def test_get_app_with_resources_and_conditions(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_APP_GET_JSON, stderr=""),
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
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_APP_GET_MINIMAL_JSON, stderr=""),
    ]

    result = argocd_lint.get_argocd_app("simple-app", context="my-ctx")

    assert result.success is True
    assert result.name == "simple-app"
    assert result.resources is None
    assert result.conditions is None


def test_get_app_passes_kube_context_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=ARGOCD_APP_GET_MINIMAL_JSON, stderr=""),
    ]

    argocd_lint.get_argocd_app("my-app", context="prod-cluster")

    cmd = mock_run.call_args_list[1][0][0]
    assert "--core" in cmd
    assert "--kube-context" in cmd
    assert "prod-cluster" in cmd
    assert "my-app" in cmd


def test_get_app_passes_namespace_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=ARGOCD_APP_GET_MINIMAL_JSON, stderr=""
    )

    argocd_lint.get_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    cmd = mock_run.call_args[0][0]
    assert "--namespace" in cmd
    assert "argo-cd" in cmd


def test_get_app_command_failure(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="app 'missing' not found"),
    ]

    result = argocd_lint.get_argocd_app("missing", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_get_app_argocd_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        FileNotFoundError("argocd"),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_get_app_timeout(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.TimeoutExpired(cmd="argocd", timeout=60),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "Timeout" in (result.error or "")


def test_get_app_json_parse_error(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "parse" in (result.error or "").lower()


def test_get_app_unexpected_format(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout='"just a string"', stderr=""),
    ]

    result = argocd_lint.get_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "Unexpected" in (result.error or "")


# diff_argocd_app tests


def test_diff_app_in_sync(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.in_sync is True
    assert result.diff_output == ""


def test_diff_app_has_diff(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=1, stdout=ARGOCD_DIFF_OUTPUT, stderr=""),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is True
    assert result.in_sync is False
    assert "replicas" in result.diff_output


def test_diff_app_error(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="FATA[0000] app not found"),
    ]

    result = argocd_lint.diff_argocd_app("missing", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_diff_app_passes_kube_context_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    argocd_lint.diff_argocd_app("my-app", context="prod-cluster")

    cmd = mock_run.call_args_list[1][0][0]
    assert "--core" in cmd
    assert "--kube-context" in cmd
    assert "prod-cluster" in cmd
    assert "my-app" in cmd


def test_diff_app_passes_namespace_flag(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    argocd_lint.diff_argocd_app("my-app", context="my-ctx", namespace="argo-cd")

    cmd = mock_run.call_args[0][0]
    assert "--namespace" in cmd
    assert "argo-cd" in cmd


def test_diff_app_argocd_not_found(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        FileNotFoundError("argocd"),
    ]

    result = argocd_lint.diff_argocd_app("my-app", context="my-ctx")

    assert result.success is False
    assert "not found" in (result.error or "")


def test_diff_app_timeout(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
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


# Edge case: non-list JSON response for app list


def test_list_apps_non_list_json(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout='{"not": "a list"}', stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


def test_list_apps_non_dict_items(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        _DETECT_OK,
        subprocess.CompletedProcess(args=[], returncode=0, stdout='["not a dict", 42]', stderr=""),
    ]

    result = argocd_lint.list_argocd_apps(context="my-ctx")

    assert result.success is True
    assert len(result.apps) == 0


# Edge case: non-dict resource in get_app


def test_get_app_with_non_dict_resource(mocker):
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
