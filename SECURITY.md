# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue
2. Email **security@sopho.tech** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. You will receive a response within 48 hours
4. A fix will be developed and released as a patch version

## Scope

This project wraps external CLI tools (kubectl, helm, flux, kubeconform) via subprocess. Security concerns include:

- **Path traversal** in user-provided file paths
- **Command injection** via unsanitized inputs to subprocess calls
- **Sensitive data exposure** in validation output

## Security Scanning

This project uses automated security scanning:

- **CodeQL** — Static analysis (SAST)
- **Bandit** — Python security linting
- **Trivy** — Container image CVE scanning
- **Gitleaks** — Secret detection
- **pip-audit** — Dependency vulnerability auditing
- **Cosign** — Container image signing
- **OpenSSF Scorecard** — Security health metrics
