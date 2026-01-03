# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

### Private Disclosure (Preferred)

Use [GitHub's private vulnerability reporting](https://github.com/lyehe/porterminal/security/advisories/new):

1. Go to **Security** → **Advisories** → **New draft advisory**
2. Fill in the vulnerability details
3. Submit for review

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Any suggested fixes (optional)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Resolution target**: Within 90 days (depending on severity)

### Scope

This policy applies to:
- The `porterminal` Python package
- The frontend TypeScript code
- WebSocket communication
- Cloudflare tunnel integration

### Out of Scope

- Vulnerabilities in Cloudflare's infrastructure
- Issues in third-party dependencies (report to upstream)
- Social engineering attacks

## Security Considerations

Porterminal exposes terminal access over the network. Users should:
- Only run on trusted networks
- Use the URL-based authentication token
- Be aware that terminal output is transmitted over WebSocket
