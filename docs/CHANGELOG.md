# Changelog

All notable changes to Porterminal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-08-13

### Added

- **Per-launch access path** - Every start creates a 128-bit random URL path
  included in the displayed link, copied text, and QR code.
- **Protected-path browser verification** - CI now boots the built frontend on
  the real ASGI server and verifies default-deny HTTP routing, static/API paths,
  both WebSocket paths, and copied agent links in Chromium.

### Changed

- **Manual MCP driver URL** - `scripts/agent_drive.py` now requires and validates
  the complete protected `/<access-code>/mcp` URL instead of falling back to an
  unreachable bare endpoint.
- **Browser password lifecycle** - A remembered plaintext password is stored
  with its complete protected URL and returned only for an exact match, avoiding
  collisions from the legacy 32-bit hashed keys. A successful save retires
  stale legacy/current Porterminal auth entries on the same origin. Clearing a
  remembered password removes all Porterminal auth entries while preserving
  unrelated localStorage data.
- **Application factory migration (breaking)** - Embedders must call
  `create_app(..., access_code=...)`. Direct uses of the environment-backed ASGI
  factory must set a valid `PORTERMINAL_ACCESS_CODE`; missing or invalid values
  now fail startup. The `ptn` CLI supplies this automatically, and clients must
  use the resulting complete `/<access-code>/...` URLs.

### Security

- **Whole-application capability boundary** - Browser pages, static assets,
  WebSockets, MCP, REST, discovery, and health checks are reachable only below
  the exact per-launch path. The bare hostname and incorrect paths return 404,
  and rejected WebSocket upgrades close before reaching terminal handlers.
- **Capability-link privacy** - Protected pages send a no-referrer policy, and
  browser credential storage is scoped to the per-launch URL path.
- **Fail-closed application construction** - Every application factory call now
  requires a valid access code, so alternate ASGI and embedding paths cannot
  silently expose bare routes.
- **Hardened background startup** - Parent and child coordinate through a
  randomized private temporary directory and atomically publish only the
  credential-free base URL; the parent validates it, adds its known access code,
  and cleans up the rendezvous on every handled exit path. POSIX terminal
  disconnects (`SIGHUP`) take the same cleanup path as `SIGTERM`, and Windows
  failed-start cleanup verifies `taskkill` completion before falling back to the
  retained process handle.

## [1.0.7] - 2026-08-02

### Changed

- **CLI package boundary** - Moved runtime orchestration behind the existing
  `porterminal.main` entry point so importing package metadata no longer loads
  the CLI, tunnel, repository, and process-management stack.
- **Maintainable CLI lifecycle** - Decomposed startup, tunnel reporting,
  foreground controls, and cleanup into typed helpers while preserving the
  existing command-line interface and output.
- **Responsive update checks** - Runs the existing cached PyPI update lookup
  outside the ASGI event loop without changing its response contract.
- **Strict management requests** - Settings, button, and password writes now
  reject unknown fields, nulls, and type coercion with standard HTTP 422
  validation responses; the browser renders those field errors readably.
- **Refactor safeguards** - Added CLI, route, terminal lifecycle, reconnection,
  and flow-control characterization tests and expanded Pyright coverage to the
  complete Python package on Windows, Linux, and macOS.
- **Verification and release integrity** - Added backend and frontend coverage
  artifacts, declared-lower-bound tests, commit-pinned CI actions, checksum-
  verified CI tools, and verified wheel/source archives plus SHA-256 checksums
  on GitHub releases.
- **Binary installation floors** - Raised the `pywinpty` and `PyYAML` minimums
  to releases with wheels for both supported Python versions, avoiding
  unexpected local Rust/C extension builds in fresh installs.
- **Configuration client** - Consolidated password-management response handling
  behind one typed request path without changing its API calls or UI results.

### Security

- **Local shutdown boundary** - Shutdown authorization now uses the direct TCP
  peer instead of spoofable Cloudflare headers. Uvicorn proxy-header rewriting
  is disabled so only the local server or its loopback Cloudflare tunnel origin
  can reach the administrative shutdown path.
- **Patched dependency lock** - Refreshed Starlette, python-dotenv, Pygments,
  Click, filelock, virtualenv, pytest, and the compatible FastAPI release to
  versions that resolve all dependency advisories reported before publication;
  raised the FastAPI, Starlette, and pytest floors so minimum-version installs
  cannot reintroduce the affected releases.

## [1.0.6] - 2026-08-01

### Added

- **Release verification** - Added a reusable cross-platform workflow that runs
  linting, formatting, type checks, backend and frontend tests, a real-browser
  smoke test, and an isolated install of the built wheel before publication.
- **Regression coverage** - Added tests for configuration persistence, route
  contracts, terminal connection behavior, input gestures, and management UI
  state.

### Changed

- **Configuration ownership** - Centralized discovery, validation, and atomic
  persistence in `ConfigStore`, while preserving unknown configuration fields.
- **Application boundaries** - Split backend routes and frontend bootstrap
  responsibilities into focused modules and introduced a typed PTY factory
  boundary.
- **Frontend toolchain** - Updated the build and test dependencies, eliminated
  known npm audit findings, and split terminal assets into a dedicated chunk.

### Fixed

- **ASGI composition** - Creates one environment-aware dependency container at
  startup, reuses injected containers, and reliably unwinds partially started
  services when startup fails.
- **Packaged frontend** - Development and browser-test servers no longer delete
  production bundles, and distribution verification rejects missing referenced
  assets or a server that cannot answer its installed `/health` endpoint.

## [1.0.5] - 2026-07-31

### Fixed

- **Fresh tool installs** - Migrated the server and client integrations to the
  MCP 2.x API so `uvx ptn` and newly upgraded tool environments no longer fail
  at startup after resolving MCP 2.0.

## [1.0.2] - 2026-06-26

### Changed

- **Startup copy hints** - Split the CLI copy instructions into separate `c`
  and `u` lines so they stay readable beside the QR code.
- **Agent REST guidance** - `/llms.txt` now warns agents that local shell
  table rendering can visually truncate long REST `output` fields.

### Documentation

- Aligned README, architecture, and agent-access copy around the same "agent
  instructions and URL" wording used by the CLI.

### Maintenance

- Ignored local `porterminal/third_party/` checkouts so scratch vendor clones do
  not pollute `git status`.

## [0.5.3] - 2026-01-20

### Fixed

- **Compose placeholder** - Placeholder now correctly shows when textarea loses focus
- **Update detection** - Better uvx detection for showing correct upgrade command

## [0.5.2] - 2026-01-19

### Added

- **Version overlay on startup** - Shows current version and update availability when app loads
  - Displays upgrade command with copy button when update is available
  - Shows "up to date" confirmation otherwise
  - Tap anywhere to dismiss

## [0.5.1] - 2026-01-18

### Changed

- **Compose mode enhancements**
  - Rainbow animated button (CMY color cycling) - slow when off, fast neon glow when active
  - Updated placeholder with emoji icons for type/voice input
  - Send button now sends text followed by Enter (with delay for reliability)
- **Help panel redesigned** - Compact layout with close button only, no header

## [0.5.0] - 2026-01-16

### Added

- **Compose mode** - New text input mode for mobile-friendly typing
  - Toggle with ▤ button in the tab bar
  - Type in a native text box with autocorrect, suggestions, and cursor positioning
  - Press Enter (⏎) to send newline, or type text and tap Send (➤) to transmit
  - Quick toolbar buttons (Esc, Ctrl, arrows) still send directly to terminal
  - State persists across page reloads
- **ResizeObserver for terminal fitting** - Terminal now properly resizes when compose mode toggles or viewport changes

### Changed

- Simplified viewport handling - ResizeObserver is now single source of truth for terminal refits
- Removed redundant window resize and orientationchange handlers
- ComposeInput component simplified (200 → 99 lines)

### Fixed

- Terminal no longer gets hidden under compose input area
- Consistent UI styling across auth, disconnect, and compose components (subtle shadows, no heavy borders)

## [0.4.8] - 2026-01-14

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

[Unreleased]: https://github.com/lyehe/porterminal/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/lyehe/porterminal/compare/v1.0.7...v1.1.0
[1.0.7]: https://github.com/lyehe/porterminal/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/lyehe/porterminal/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/lyehe/porterminal/compare/v1.0.4...v1.0.5
[1.0.2]: https://github.com/lyehe/porterminal/compare/v1.0.1...v1.0.2
[0.5.0]: https://github.com/lyehe/porterminal/compare/v0.4.8...v0.5.0
[0.4.8]: https://github.com/lyehe/porterminal/compare/v0.4.1...v0.4.8
[0.4.1]: https://github.com/lyehe/porterminal/compare/v0.4.0...v0.4.1
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
