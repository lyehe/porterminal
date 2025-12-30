# Changelog

All notable changes to Porterminal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2024-12-30

### Fixed
- Shutdown button now works from Cloudflare tunnel (was returning 403)
- cloudflared PATH detection after package manager installation (Windows/Linux/macOS)
- Duplicate text rendering when terminal screen refreshes (output buffer fix)
- Connection state machine prevents orphaned WebSocket connections

### Changed
- Improved README with complete usage examples and options table
- Enhanced configuration documentation with shell customization examples
- Tab UI more compact (shows only tab number)

### Added
- Auto-detect cloudflared install location after winget/apt/brew install
- Prompts to restart terminal if cloudflared not found in PATH after install

## [0.1.0] - 2024-12-28

### Added
- Initial release
- Web-based terminal with xterm.js
- Mobile-optimized touch interface with virtual keyboard
- Modifier key support (Ctrl, Alt) with sticky/locked modes
- Multi-tab terminal sessions
- Session persistence with unlimited reconnection window
- Cloudflare Quick Tunnel integration with QR code display
- Cross-platform PTY support (Windows via pywinpty, Unix via pty)
- Auto-detection of available shells (PowerShell, CMD, WSL, Bash)
- Environment variable sanitization (blocks API keys and secrets)
- Token bucket rate limiting (100 req/sec, 500 burst)
- Output batching for efficient data transfer
- Custom button configuration via config.yaml
- Service worker for offline caching
- Cloudflare Access integration support

### Security
- Environment sanitization blocks sensitive variables (AWS, GitHub, OpenAI keys, etc.)
- Session isolation per user via Cloudflare Access email
- Rate limiting on WebSocket input
- Admin privilege warnings on Windows

[Unreleased]: https://github.com/lyehe/porterminal/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/lyehe/porterminal/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lyehe/porterminal/releases/tag/v0.1.0
