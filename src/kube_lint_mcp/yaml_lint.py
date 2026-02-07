"""YAML syntax validation for Kubernetes manifests."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

YAML_EXTENSIONS = {".yaml", ".yml"}


@dataclass
class YamlFileResult:
    """Validation result for a single YAML file."""

    file: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    document_count: int = 0


@dataclass
class YamlValidationResult:
    """Overall result of YAML validation."""

    path: str
    passed: bool
    files: list[YamlFileResult] = field(default_factory=list)
    total_files: int = 0
    valid_files: int = 0
    invalid_files: int = 0


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that detects duplicate keys in mappings."""


def _check_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[str, object]:
    """Construct a mapping while checking for duplicate keys."""
    mapping: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)  # type: ignore[no-untyped-call]
        if key in mapping:
            mark = key_node.start_mark
            raise yaml.MarkedYAMLError(
                problem=f"duplicate key: {key!r}",
                problem_mark=mark,
            )
        mapping[key] = loader.construct_object(value_node)  # type: ignore[no-untyped-call]
    return mapping


_DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _check_duplicate_keys,
)


def _check_tabs(content: str) -> list[str]:
    """Check for tab characters used as indentation."""
    warnings = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.lstrip("\t")
        if len(stripped) < len(line):
            warnings.append(f"line {i}: tab character used for indentation")
    return warnings


def _find_yaml_files(path: str) -> list[str]:
    """Find all YAML files in a path (file or directory)."""
    p = Path(path)
    if p.is_file():
        if p.suffix in YAML_EXTENSIONS:
            return [str(p)]
        return []

    if p.is_dir():
        files = []
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix in YAML_EXTENSIONS:
                files.append(str(f))
        return files

    return []


def validate_file(file_path: str) -> YamlFileResult:
    """Validate a single YAML file for syntax errors, duplicate keys, and tabs."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError as e:
        return YamlFileResult(
            file=file_path,
            valid=False,
            errors=[f"Cannot read file: {e}"],
        )

    errors: list[str] = []
    warnings: list[str] = []

    # Check for tab indentation
    warnings.extend(_check_tabs(content))

    # Parse all documents in the file
    doc_count = 0
    try:
        for _doc in yaml.load_all(content, Loader=_DuplicateKeyLoader):
            doc_count += 1
    except yaml.YAMLError as e:
        if hasattr(e, "problem_mark") and e.problem_mark is not None:
            mark = e.problem_mark
            msg = getattr(e, "problem", str(e))
            errors.append(f"line {mark.line + 1}, column {mark.column + 1}: {msg}")
        else:
            errors.append(str(e))

    return YamlFileResult(
        file=file_path,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        document_count=doc_count,
    )


def validate_yaml(path: str) -> YamlValidationResult:
    """Validate YAML files at the given path.

    Args:
        path: Path to a YAML file or directory containing YAML files.

    Returns:
        YamlValidationResult with per-file details and counts.
    """
    files = _find_yaml_files(path)

    if not files:
        return YamlValidationResult(path=path, passed=True)

    results = [validate_file(f) for f in files]
    valid_count = sum(1 for r in results if r.valid)
    invalid_count = sum(1 for r in results if not r.valid)

    return YamlValidationResult(
        path=path,
        passed=invalid_count == 0,
        files=results,
        total_files=len(results),
        valid_files=valid_count,
        invalid_files=invalid_count,
    )
