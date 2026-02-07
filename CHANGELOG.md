# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `py.typed` marker for PEP 561 inline type support
- mypy strict type checking with CI integration
- CHANGELOG.md

### Changed

- Replaced flake8 with ruff for linting (adds isort, pyupgrade, bugbear, simplify rules)

### Removed

- `.flake8` configuration file

## [0.4.3] - 2026-02-03

### Fixed

- Release workflow fixes
- Removed Docker Hub publishing (GHCR only)

## [0.4.2] - 2026-01-28

### Changed

- Refactored error handling across all lint modules
- Refactored test suite structure
- Updated README
- Consolidated CI actions

## [0.4.1] - 2026-01-27

### Fixed

- CI and release workflow fixes
- OSV scanner configuration

## [0.4.0] - 2026-01-26

### Changed

- Migrated Docker base image from DHI to `python:3.13-slim`
- Updated CI actions and approver configuration
- Updated README

## [0.3.9] - 2026-01-20

### Fixed

- Release workflow logic updates

## [0.3.8] - 2026-01-19

### Changed

- Bumped actions/stale from 9.1.0 to 10.1.1
- Bumped dessant/lock-threads from 5.0.1 to 6.0.0
- Bumped sigstore/cosign-installer
- Bumped actions/attest-build-provenance from 2 to 3
- Bumped actions/dependency-review-action

## [0.3.7] - 2026-01-18

### Fixed

- Security action updates
- Compliance issues addressed

## [0.3.6] - 2026-01-17

### Added

- Additional CI and quality actions (bandit, pip-audit, hadolint, gitleaks, dockle, checkov)

## [0.3.5] - 2026-01-15

### Added

- Housekeeping actions (stale, lock)
- Trivy container scanning

## [0.3.4] - 2026-01-14

### Added

- Supply chain security actions (scorecard, dependency-review, cosign)

### Fixed

- Codecov and CI permissions configuration

## [0.3.3] - 2026-01-13

### Fixed

- Release action updates

## [0.3.2] - 2026-01-12

### Fixed

- Release workflow trigger fixes

## [0.3.1] - 2026-01-12

### Fixed

- Publish step trigger on release

## [0.3.0] - 2026-01-11

### Added

- Kustomize overlay validation (`kustomize_dryrun` tool)
- Kubeconform offline schema validation (`kubeconform_validate` tool)
- Helm chart validation (`helm_dryrun` tool)
- Shared `dryrun` module to reduce code duplication

### Changed

- Refactored repetitive validation code into shared utilities

## [0.2.0] - 2026-01-10

### Added

- Initial release
- FluxCD manifest dry-run validation (`flux_dryrun` tool)
- Flux health check (`flux_check` tool)
- Flux reconciliation status (`flux_status` tool)
- Context selection (`select_kube_context`, `list_kube_contexts` tools)
- Docker image with kubectl, helm, flux, kubeconform
- CI pipeline with tests and coverage
- Release workflow with PyPI OIDC publishing

[Unreleased]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.4.3...HEAD
[0.4.3]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.9...v0.4.0
[0.3.9]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/sophotechlabs/kube-lint-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sophotechlabs/kube-lint-mcp/releases/tag/v0.2.0
