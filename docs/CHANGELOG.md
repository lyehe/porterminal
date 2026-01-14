# Changelog

All notable changes to Porterminal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Config from URL/file** - `ptn -i` can now fetch config templates from URLs or local files
- **Expanded script discovery** - Improved detection of project scripts with shared helpers

### Fixed

- **Paste rate limit** - Increased rate limit defaults from 500 bytes to 16KB burst, fixing "rate limit exceeded" errors when pasting text

## [0.4.1] - 2026-01-12

### Added

- **Auto-discover project scripts** - `ptn -i` now scans for project files and adds discovered scripts as buttons in row 2
  - Detects `package.json` scripts (build, dev, test, lint, etc.)
  - Detects `pyproject.toml` scripts (`[project.scripts]` and `[tool.poetry.scripts]`)
  - Detects `Makefile` targets (build, test, clean, etc.)
  - Only includes explicitly defined scripts, not generic commands
- **Configurable button rows** - Buttons can now specify which toolbar row to appear in (1-10)
  - `row: 1` (default) places button in first custom row
  - `row: 2` places button in second custom row
  - Rows are created dynamically as needed

### Changed

- `ptn -i` now launches the server after creating config (previously exited immediately)
- Default config buttons updated to AI coding tools: `/new`, `/init`, `/resume`, `/compact`, `claude`, `codex`

### Fixed

- **Nushell/Fish compatibility** - Added missing environment variables (`USER`, `SHELL`, `XDG_*`) that modern shells need for proper initialization ([#13](https://github.com/lyehe/porterminal/issues/13))
- Code simplification: Extracted button creation helpers in frontend for better maintainability

## [0.4.0] - 2026-01-12

This release focuses on mobile experience improvements and robust shell support.

### Added

#### Shell Support
- **Dynamic shell detection** - Supports any shell (Nushell, Xonsh, Elvish, Ion, Oil, etc.) by automatically detecting shells from the `$SHELL` environment variable ([#13](https://github.com/lyehe/porterminal/issues/13))
  - Unknown shells are dynamically added to the shell list
  - User's preferred shell appears first in the dropdown
  - Validates shell exists before adding to list
  - No code changes needed to support new shells

#### Terminal Output
- **Alt-screen buffer handling** - Proper handling of applications that use the alternate screen buffer (vim, less, htop, nano, tmux)
  - Snapshots normal buffer on alt-screen entry
  - Restores normal buffer on alt-screen exit
  - Detects DEC Private Mode sequences (`?47h`, `?1047h`, `?1049h`)
  - Clean screen transitions without history loss
- **Watermark-based flow control** - Improved output buffering with high/low watermark system
  - Prevents overwhelming the frontend during high-output scenarios (e.g., `cat large_file.txt`)
  - 100KB high watermark triggers pause, 10KB low watermark resumes
  - Early buffer (1MB) during connection handshake for initial screen draw
  - Proper backpressure signaling to backend

#### Mobile Touch Experience
- **Momentum scrolling** - Physics-based smooth scrolling on touch devices
  - Velocity tracking with exponential moving average smoothing
  - Natural deceleration (0.95 friction per frame)
  - Accumulator pattern for fractional line scrolling
  - Respects terminal scroll boundaries
- **Pinch-to-zoom** - Zoom terminal text with pinch gestures
  - Uses CSS `transform: scale()` during gesture (no reflow)
  - Applies actual font size change on gesture end
  - Font size range: 10-24px
  - Preserves scroll position (stays at bottom if was at bottom)
- **Mobile keyboard control** - `setKeyboardEnabled` API to prevent virtual keyboard from appearing during text selection
  - Sets textarea to readonly during selection
  - Blurs terminal to dismiss keyboard
  - Re-enables on selection complete

#### UI Improvements
- **CopyButton API** - `isVisible()` and `setOnHide()` callbacks for better gesture integration
  - Allows gesture system to check button visibility
  - Callback on hide for terminal refocus
- **TextViewOverlay enhancements** - Improved text selection overlay for mobile
  - Better touch target sizing
  - Clearer selection feedback

#### Documentation
- **Buffer architecture** - Comprehensive `docs/buffer.md` documenting the entire data flow:
  - PTY read (4KB) → Session buffer (1MB) → Batch buffer (16KB/16ms) → WebSocket → Frontend early buffer → Watermark flow control → xterm.js
- **Frontend features guide** - `docs/frontend_features.md` covering:
  - Dual WebSocket architecture
  - Gesture recognition system
  - Three-state modifier system
  - Connection handshake protocol
  - iOS workarounds and gotchas
- **Debug documentation** - `docs/debug.md` and debug case studies:
  - Touch scrolling implementation
  - Pinch-zoom stale text fix
  - Frontend design fixes

#### Testing
- **Output buffer tests** - New `tests/domain/test_output_buffer.py` with comprehensive coverage:
  - Basic operations, size limits, clear screen handling
  - Alt-screen enter/exit transitions
  - Nested alt-screen handling
  - Buffer snapshot/restore

### Changed
- **Upgraded to xterm.js 6.0** - Latest terminal emulator with improved performance and rendering
- **ConnectionService refactor** - Cleaner WebSocket state management with explicit states
- **GestureRecognizer improvements** - Better touch event handling, cleaner state machine
- **ManagementService simplification** - Reduced complexity in tab management
- **TerminalService cleanup** - Streamlined output handling and batch flush logic
- **Domain layer cleanup** - Removed unused barrel exports from domain packages
- **KeyMapper updates** - Better special key handling
- **Vite config updates** - Improved build configuration

### Fixed
- Keyboard no longer flickers during text selection on mobile
- Copy button properly integrates with gesture system
- Shell detection no longer ignores valid shells not in hardcoded list
- Alt-screen apps (vim, htop) no longer corrupt buffer history
- Scroll position preserved correctly during font size changes
- Touch events properly deduplicated (no ghost taps)

### Removed
- Unused environment sanitizer tests (logic moved to integration tests)
- Redundant domain service exports

## [0.3.4] - 2026-01-05

### Fixed
- Windows auto-update error when checking for new versions

## [0.3.3] - 2026-01-04

### Changed
- Password protection warning now highlighted for better visibility

## [0.3.2] - 2026-01-03

### Fixed
- Respect user's `$SHELL` environment variable for default shell on macOS/Linux ([#12](https://github.com/lyehe/porterminal/pull/12) by [@iamd3vil](https://github.com/iamd3vil))

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

[Unreleased]: https://github.com/lyehe/porterminal/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/lyehe/porterminal/compare/v0.3.4...v0.4.0
[0.3.4]: https://github.com/lyehe/porterminal/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/lyehe/porterminal/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/lyehe/porterminal/compare/v0.3.1...v0.3.2
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
