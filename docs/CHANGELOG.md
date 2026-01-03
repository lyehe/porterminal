# Changelog

All notable changes to Porterminal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-01-03

### Fixed
- Add 1s startup delay before opening browser to prevent Cloudflare IP blocking

## [0.3.0] - 2026-01-03

### Added
- **Password protection** - Secure terminal access with a disposable session password
  - `-p` flag prompts for password at startup
  - `-dp` flag toggles password requirement in config (persistent)
  - Password hashed with bcrypt, stored only in memory (never written to disk)
  - Auth overlay UI with retry support
  - Configurable retry limits (`security.max_auth_attempts`)
- New `docs/security.md` with authentication documentation

### Security
- WebSocket authentication protocol with `auth_required`/`auth_success`/`auth_failed` messages
- Failed auth attempts tracked per connection with configurable limits
- Server shuts down with warning after max failed attempts (prevents brute force)
- Password is per-session (server restart = new password)

## [0.2.7] - 2026-01-03

### Fixed
- Cloudflared auto-install now works on Linux Mint and other Ubuntu derivatives
- Uses Cloudflare's "any" distribution instead of codename detection (fixes [#11](https://github.com/lyehe/porterminal/issues/11))

## [0.2.6] - 2026-01-03

### Added
- Shell detection from Windows Terminal `settings.json`
- Visual Studio Developer shells detection (Dev CMD, Dev PS)
- Abbreviated shell names for cleaner display (e.g., "Windows PowerShell" → "WinPS")

### Fixed
- Ctrl+C now properly kills server and all child processes on Windows (uses `taskkill /T`)
- Keyboard now hides when clicking shutdown button on mobile

### Changed
- Shell detection priority: Windows Terminal profiles → VS shells → hardcoded defaults

## [0.2.5] - 2026-01-02

### Added
- Update settings in shared config (`ptn.yaml`):
  - `update.notify_on_startup`: enable/disable startup notification (default: true)
  - `update.check_interval`: seconds between PyPI checks (default: 86400 = 24h)
- Test infrastructure for domain, application, and infrastructure layers

### Changed
- Consolidated update system: merged `update_checker.py` into `updater.py` (~260 lines removed)
- Fixed execution order: CLI args now parsed before update check (flags always work)
- Single cache location: `~/.ptn/update_check.json`
- Notification-only updates: no more auto-exec, just prints message
- Improved server/tunnel exit messages (cleaner shutdown feedback)

### Fixed
- Version comparison now handles `0.9` vs `0.10` correctly (was using string compare)
- Install method detection checks executable path, not just binary existence
- Narrowed exception handling (specific types instead of `except Exception`)

### Removed
- Auto-update exec behavior (was replacing process mid-run)
- `update_checker.py` (functionality merged into `updater.py`)
- Second cache location at `~/.cache/porterminal/`

## [0.2.4] - 2025-01-02

### Added
- `auto_update` option in `~/.ptn/ptn.yaml` (disabled by default)
- Global config auto-generated on first run

## [0.2.3] - 2025-01-02

### Added
- `--init` flag to create `.ptn/ptn.yaml` config in current directory

## [0.2.2] - 2025-01-02

### Added
- Auto-update: checks PyPI daily and updates via `uvx --refresh` if newer version available

## [0.2.1] - 2025-01-02

### Added
- Terminal size syncing across clients sharing a session (resize_sync message)

### Changed
- Reduced debug logging verbosity in terminal service

## [0.2.0] - 2025-01-02

### Added
- Custom buttons now render in dedicated third toolbar row
- Config file search paths: `PORTERMINAL_CONFIG_PATH` env var, `./ptn.yaml`, `./.ptn/ptn.yaml`, `~/.ptn/ptn.yaml`

### Fixed
- Race condition when new clients connect during active broadcast (duplicate output)
- Session locks now ensure buffer replay and broadcast are atomic

### Changed
- Config file renamed from `config.yaml` to `ptn.yaml`
- Centralized key configuration in `frontend/src/config/keys.ts` (single source of truth)
- New Toolbar component renders buttons from config
- Simplified frontend architecture (removed ~700 lines of code)
- README updated with demo video and improved "Why" section

### Removed
- PWA support (service worker and manifest.json) - simplifies deployment
- `generate_favicon.py` - no longer needed

## [0.1.8] - 2025-01-01

### Fixed
- iOS keyboard improvements: `enterkeyhint="send"` for Send button
- Safari 18+ inline prediction control via `writingsuggestions="false"`
- Restored iOS backspace fix (beforeinput handler for delete key)

### Changed
- Cleaned up stale frontend assets

## [0.1.7] - 2025-01-01

### Changed
- README updated with uv installation instructions
- Fixed PyPI package name references in documentation

## [0.1.6] - 2025-01-01

### Changed
- Streamlined versioning with `hatch-vcs` (git tag-based, single source of truth)
- Removed hardcoded version strings from multiple files

### Fixed
- CI workflow for master branch and correct CLI command

## [0.1.5] - 2024-12-31

### Fixed
- Cursor positioning bug on page refresh (buffer flush race condition with xterm.js layout)
- Tab switch cursor visibility (replaced setTimeout with requestAnimationFrame)

### Changed
- README updated with installation & update instructions table

## [0.1.4] - 2024-12-31

### Added
- Text view overlay for easier text selection on mobile (via button)
- Management WebSocket for centralized tab control

### Changed
- Tab management architecture refactored to server-side state with sync to clients
- Simplified frontend by removing StorageService and barrel exports
- Cleaner domain layer with dedicated tab entities, ports, and services

### Fixed
- Tab state consistency across reconnections

## [0.1.2] - 2024-12-30

### Fixed
- Improved cloudflared install flow: shows friendly "restart terminal" message instead of error when PATH not updated

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

[Unreleased]: https://github.com/lyehe/porterminal/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/lyehe/porterminal/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/lyehe/porterminal/compare/v0.2.7...v0.3.0
[0.2.7]: https://github.com/lyehe/porterminal/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/lyehe/porterminal/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/lyehe/porterminal/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/lyehe/porterminal/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/lyehe/porterminal/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/lyehe/porterminal/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/lyehe/porterminal/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/lyehe/porterminal/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/lyehe/porterminal/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/lyehe/porterminal/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/lyehe/porterminal/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/lyehe/porterminal/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/lyehe/porterminal/compare/v0.1.2...v0.1.4
[0.1.2]: https://github.com/lyehe/porterminal/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/lyehe/porterminal/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lyehe/porterminal/releases/tag/v0.1.0
