import pathlib

import yaml

from kube_lint_mcp.yaml_lint import (
    _check_tabs,
    _find_yaml_files,
    validate_file,
    validate_yaml,
)

# _check_tabs tests


def test_check_tabs_no_tabs():
    assert _check_tabs("key: value\n  nested: ok\n") == []


def test_check_tabs_detects_tab_indentation():
    content = "key: value\n\tindented: bad\n"
    warnings = _check_tabs(content)

    assert len(warnings) == 1
    assert "line 2" in warnings[0]
    assert "tab" in warnings[0]


def test_check_tabs_multiple_lines():
    content = "\tline1\nline2\n\tline3\n"
    warnings = _check_tabs(content)

    assert len(warnings) == 2
    assert "line 1" in warnings[0]
    assert "line 3" in warnings[1]


def test_check_tabs_tab_not_at_start():
    content = "key:\tvalue\n"
    # Tab not at start of line (after non-tab chars) — not indentation
    warnings = _check_tabs(content)

    assert warnings == []


# _find_yaml_files tests


def test_find_yaml_files_single_file(tmp_path):
    f = tmp_path / "deploy.yaml"
    f.write_text("apiVersion: v1")

    assert _find_yaml_files(str(f)) == [str(f)]


def test_find_yaml_files_yml_extension(tmp_path):
    f = tmp_path / "deploy.yml"
    f.write_text("apiVersion: v1")

    assert _find_yaml_files(str(f)) == [str(f)]


def test_find_yaml_files_non_yaml_file(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("hello")

    assert _find_yaml_files(str(f)) == []


def test_find_yaml_files_directory(tmp_path):
    (tmp_path / "a.yaml").write_text("a: 1")
    (tmp_path / "b.yml").write_text("b: 2")
    (tmp_path / "c.txt").write_text("c")

    files = _find_yaml_files(str(tmp_path))

    assert len(files) == 2
    assert any("a.yaml" in f for f in files)
    assert any("b.yml" in f for f in files)


def test_find_yaml_files_empty_dir(tmp_path):
    assert _find_yaml_files(str(tmp_path)) == []


def test_find_yaml_files_nonexistent_path():
    assert _find_yaml_files("/nonexistent/path") == []


def test_find_yaml_files_sorted(tmp_path):
    (tmp_path / "c.yaml").write_text("c: 1")
    (tmp_path / "a.yaml").write_text("a: 1")
    (tmp_path / "b.yaml").write_text("b: 1")

    files = _find_yaml_files(str(tmp_path))
    names = [pathlib.Path(f).name for f in files]

    assert names == ["a.yaml", "b.yaml", "c.yaml"]


# validate_file tests


def test_validate_file_valid_yaml(tmp_path):
    f = tmp_path / "good.yaml"
    f.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n")

    result = validate_file(str(f))

    assert result.valid is True
    assert result.errors == []
    assert result.document_count == 1


def test_validate_file_multi_document(tmp_path):
    f = tmp_path / "multi.yaml"
    f.write_text("a: 1\n---\nb: 2\n---\nc: 3\n")

    result = validate_file(str(f))

    assert result.valid is True
    assert result.document_count == 3


def test_validate_file_syntax_error(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("key: [\n  unclosed\n")

    result = validate_file(str(f))

    assert result.valid is False
    assert len(result.errors) == 1
    assert "line" in result.errors[0]


def test_validate_file_duplicate_key(tmp_path):
    f = tmp_path / "dup.yaml"
    f.write_text("key: value1\nkey: value2\n")

    result = validate_file(str(f))

    assert result.valid is False
    assert len(result.errors) == 1
    assert "duplicate" in result.errors[0].lower()


def test_validate_file_tab_warning(tmp_path):
    f = tmp_path / "tabs.yaml"
    f.write_text("key: value\n\tindented: bad\n")

    result = validate_file(str(f))

    # Tabs produce warnings but file may still be valid YAML (or not, depending on parser)
    assert len(result.warnings) > 0
    assert "tab" in result.warnings[0]


def test_validate_file_unreadable(tmp_path):
    result = validate_file(str(tmp_path / "nonexistent.yaml"))

    assert result.valid is False
    assert len(result.errors) == 1
    assert "Cannot read file" in result.errors[0]


def test_validate_file_empty(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("")

    result = validate_file(str(f))

    assert result.valid is True
    assert result.document_count == 0


def test_validate_file_bad_indentation(tmp_path):
    f = tmp_path / "indent.yaml"
    f.write_text("parent:\n  child: value\n bad_indent: value\n")

    result = validate_file(str(f))

    assert result.valid is False
    assert len(result.errors) >= 1


def test_validate_file_unclosed_string(tmp_path):
    f = tmp_path / "string.yaml"
    f.write_text('key: "unclosed\n')

    result = validate_file(str(f))

    assert result.valid is False


def test_validate_file_error_without_mark(tmp_path, mocker):
    """YAML errors without a problem_mark fall back to str(e)."""
    f = tmp_path / "weird.yaml"
    f.write_text("key: value\n")

    error = yaml.YAMLError("something went wrong")
    mocker.patch("kube_lint_mcp.yaml_lint.yaml.load_all", side_effect=error)
    result = validate_file(str(f))

    assert result.valid is False
    assert "something went wrong" in result.errors[0]


# validate_yaml tests


def test_validate_yaml_all_valid(tmp_path):
    (tmp_path / "a.yaml").write_text("a: 1\n")
    (tmp_path / "b.yaml").write_text("b: 2\n")

    result = validate_yaml(str(tmp_path))

    assert result.passed is True
    assert result.total_files == 2
    assert result.valid_files == 2
    assert result.invalid_files == 0


def test_validate_yaml_has_invalid(tmp_path):
    (tmp_path / "good.yaml").write_text("a: 1\n")
    (tmp_path / "bad.yaml").write_text("key: [\n  unclosed\n")

    result = validate_yaml(str(tmp_path))

    assert result.passed is False
    assert result.total_files == 2
    assert result.valid_files == 1
    assert result.invalid_files == 1


def test_validate_yaml_no_files(tmp_path):
    result = validate_yaml(str(tmp_path))

    assert result.passed is True
    assert result.total_files == 0
    assert result.files == []


def test_validate_yaml_single_file(tmp_path):
    f = tmp_path / "deploy.yaml"
    f.write_text("apiVersion: v1\nkind: ConfigMap\n")

    result = validate_yaml(str(f))

    assert result.passed is True
    assert result.total_files == 1


def test_validate_yaml_path_stored(tmp_path):
    result = validate_yaml(str(tmp_path))

    assert result.path == str(tmp_path)
