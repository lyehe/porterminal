# Architecture

Porterminal uses hexagonal (ports & adapters) architecture for clean separation of concerns.

## Project Structure

```
porterminal/
├── __init__.py              # Entry point with CLI and main()
├── app.py                   # FastAPI application factory
├── config.py                # Configuration loading
├── composition.py           # Dependency injection composition root
├── container.py             # DI container definition
├── asgi.py                  # ASGI application
├── logging_setup.py         # Logging configuration
├── updater.py               # Auto-update functionality
│
├── domain/                  # Core business logic (NO external dependencies)
│   ├── entities/
│   │   ├── session.py       # Session entity with PTY tracking
│   │   ├── tab.py           # Tab entity (lightweight reference)
│   │   └── output_buffer.py # Output buffer for reconnection
│   ├── values/              # Value objects
│   │   ├── session_id.py
│   │   ├── tab_id.py
│   │   ├── user_id.py
│   │   ├── shell_command.py
│   │   ├── terminal_dimensions.py
│   │   ├── environment_rules.py
│   │   └── rate_limit_config.py
│   ├── services/            # Domain business logic
│   │   ├── environment_sanitizer.py
│   │   ├── rate_limiter.py
│   │   ├── session_limits.py
│   │   └── tab_limits.py
│   └── ports/               # Interfaces (contracts)
│       ├── pty_port.py      # PTY operations interface
│       ├── session_repository.py
│       └── tab_repository.py
│
├── application/             # Use cases (orchestration layer)
│   ├── services/
│   │   ├── session_service.py    # Session lifecycle management
│   │   ├── terminal_service.py   # Terminal I/O coordination
│   │   ├── tab_service.py        # Tab management
│   │   └── management_service.py # WebSocket management (control plane)
│   └── ports/
│       ├── connection_port.py    # Network connection interface
│       └── connection_registry_port.py
│
├── infrastructure/          # External adapters & implementations
│   ├── web/
│   │   └── websocket_adapter.py  # FastAPI WebSocket → ConnectionPort
│   ├── repositories/
│   │   ├── in_memory_session.py  # Session storage
│   │   └── in_memory_tab.py      # Tab storage
│   ├── registry/
│   │   └── user_connection_registry.py  # Connection tracking
│   ├── config/
│   │   └── shell_detector.py    # Detect available shells
│   ├── auth.py              # Authentication helpers
│   ├── cloudflared.py       # Tunnel management
│   └── server.py            # Uvicorn wrapper
│
├── pty/                     # Platform-specific PTY implementations
│   ├── manager.py           # SecurePTYManager wrapper
│   ├── protocol.py          # PTY protocol constants
│   ├── env.py               # Environment handling
│   ├── windows.py           # Windows (pywinpty)
│   └── unix.py              # Unix/Linux/macOS (pty module)
│
├── cli/                     # Command-line interface
│   ├── args.py              # Argument parsing
│   └── display.py           # Startup screen & QR code
│
└── static/                  # Built frontend (from npm run build)

frontend/                    # Source frontend (TypeScript/Vite)
├── src/
│   ├── main.ts              # Application bootstrap & wiring
│   ├── core/events.ts       # Event bus
│   ├── services/            # High-level service layer
│   │   ├── ConfigService.ts     # Fetch shell config
│   │   ├── ConnectionService.ts # Terminal I/O WebSocket (data plane)
│   │   ├── ManagementService.ts # Control plane WebSocket
│   │   └── TabService.ts        # Tab rendering (backend-driven)
│   ├── input/               # Keyboard handling
│   │   ├── KeyMapper.ts
│   │   ├── InputHandler.ts
│   │   └── ModifierManager.ts
│   ├── gestures/            # Touch handling
│   │   ├── GestureRecognizer.ts
│   │   ├── SelectionHandler.ts
│   │   └── SwipeDetector.ts
│   ├── clipboard/ClipboardManager.ts
│   ├── terminal/ResizeManager.ts
│   ├── ui/                  # UI components
│   │   ├── AuthOverlay.ts
│   │   ├── ConnectionStatus.ts
│   │   ├── DisconnectOverlay.ts
│   │   ├── TextViewOverlay.ts
│   │   └── Toolbar.ts
│   └── types/index.ts
└── index.html
```

## Hexagonal Layers

### Layer 1: Domain (Core Business Logic)

**Location**: `porterminal/domain/`

Zero external dependencies. Encapsulates business rules with pure value objects and entities.

**Key Components**:
- **Entities**: `Session` (with PTY and output buffer), `Tab` (lightweight reference)
- **Values**: `SessionId`, `UserId`, `ShellCommand`, `TerminalDimensions`, `RateLimitConfig`
- **Ports**: `PTYPort`, `SessionRepository`, `TabRepository`
- **Services**: `EnvironmentSanitizer`, `TokenBucketRateLimiter`, `SessionLimitChecker`

**Example Port**:
```python
class PTYPort(ABC):
    @abstractmethod
    def spawn(self) -> None: ...
    @abstractmethod
    def read(self, size: int = 4096) -> bytes: ...
    @abstractmethod
    def write(self, data: bytes) -> None: ...
    @abstractmethod
    def resize(self, dimensions: TerminalDimensions) -> None: ...
    @abstractmethod
    def is_alive(self) -> bool: ...
    @abstractmethod
    def close(self) -> None: ...
```

### Layer 2: Application (Use Cases)

**Location**: `porterminal/application/`

Orchestrates domain logic with infrastructure. Manages lifecycle and WebSocket message flow.

**Key Services**:

| Service | Responsibility |
|---------|----------------|
| `SessionService` | Create/reconnect/destroy sessions, PTY lifecycle |
| `TabService` | Tab CRUD operations with validation |
| `TerminalService` | Terminal I/O coordination, multi-client support |
| `ManagementService` | Control plane WebSocket message handling |

### Layer 3: Infrastructure (Adapters)

**Location**: `porterminal/infrastructure/`

Implements ports with concrete technology.

| Component | Purpose |
|-----------|---------|
| `FastAPIWebSocketAdapter` | Adapts FastAPI WebSocket to `ConnectionPort` |
| `InMemorySessionRepository` | Session storage |
| `InMemoryTabRepository` | Tab storage |
| `UserConnectionRegistry` | Tracks connections for broadcasting |
| `SecurePTYManager` | Platform-specific PTY wrapper |

## Dual WebSocket Architecture

Porterminal uses two separate WebSocket connections:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Client                                     │
│  ┌───────────────────────┐         ┌───────────────────────┐        │
│  │  ManagementService    │         │  ConnectionService    │        │
│  │  (Control Plane)      │         │  (Data Plane)         │        │
│  └───────────┬───────────┘         └───────────┬───────────┘        │
└──────────────│─────────────────────────────────│────────────────────┘
               │                                 │
               ▼                                 ▼
┌──────────────────────────┐     ┌────────────────────────────────────┐
│     /ws/management       │     │  /ws?tab_id=...&session_id=...    │
│  - Tab create/close      │     │  - Binary terminal I/O            │
│  - State sync            │     │  - Resize messages                │
│  - Auth challenges       │     │  - Heartbeat                      │
└──────────────────────────┘     └────────────────────────────────────┘
```

### Management WebSocket (`/ws/management`)

Control plane for tab operations:

```json
// Client → Server
{"type": "create_tab", "request_id": "...", "shell_id": "bash"}
{"type": "close_tab", "request_id": "...", "tab_id": "..."}
{"type": "rename_tab", "request_id": "...", "tab_id": "...", "name": "..."}

// Server → Client
{"type": "tab_state_sync", "tabs": [...]}
{"type": "tab_state_update", "changes": [...]}
{"type": "create_tab_response", "request_id": "...", "success": true, "tab": {...}}
```

### Data WebSocket (`/ws`)

Data plane for terminal I/O:

- **Binary messages**: Raw terminal input/output bytes
- **JSON messages**:
```json
{"type": "resize", "cols": 120, "rows": 30}
{"type": "ping"}
{"type": "pong"}
{"type": "session_info", "session_id": "...", "shell": "..."}
{"type": "resize_sync", "cols": 120, "rows": 30}
```

## Data Model

```
User (identified by email from Cloudflare Access)
  ├── Session 1 (PTY process alive)
  │   ├── Tab 1 (reference to Session 1)
  │   ├── Tab 2 (reference to Session 1)
  │   └── Output Buffer (for reconnection)
  ├── Session 2 (PTY process alive)
  │   └── Tab 3 (reference to Session 2)
  └── ...
```

## Multi-Client Session Support

Multiple clients can connect to the same session:

- Single PTY read loop per session (started by first client)
- Output broadcasted to all connected clients
- Input from any client goes to same PTY
- Lock-protected buffer replay on new client connection
- Multi-client resize rejection (maintains consistency)

```python
# TerminalService internals
_session_connections: dict[str, set[ConnectionPort]]  # All clients per session
_session_read_tasks: dict[str, asyncio.Task]          # One read loop per session
_session_locks: dict[str, asyncio.Lock]               # Race condition prevention
```

## Dependency Injection

**Composition Root**: `porterminal/composition.py`
- Single place where all dependencies are created and wired
- Creates container with all services
- Binds interfaces to implementations

**Container**: `porterminal/container.py`
- Immutable dataclass holding all wired dependencies
- Type-safe, thread-safe

```python
async def lifespan(app: FastAPI):
    container = create_container(...)  # Startup
    app.state.container = container
    await container.session_service.start()
    yield
    await container.session_service.stop()  # Shutdown
```

## Output Batching

Optimizes data transfer:

| Data Size | Behavior |
|-----------|----------|
| < 64 bytes | Immediate flush (interactive) |
| >= 64 bytes | Delayed batching (~16ms window) |

## Rate Limiting

Token bucket algorithm:
- **Rate**: 100 messages/second
- **Burst**: 500 messages

## Session Management

- Sessions persist as long as PTY is alive (no timeout)
- Unlimited reconnection window
- Maximum 10 sessions per user (with Cloudflare Access)
- Session output buffered for reconnection

## Security Model

### Environment Sanitization

Blocked patterns:
- `*_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD`
- `AWS_*`, `AZURE_*`, `GCP_*`
- `GITHUB_*`, `OPENAI_*`, `ANTHROPIC_*`

### Session Isolation

With Cloudflare Access enabled:
- Users identified by email from CF-Access-JWT
- Each user sees only their own sessions
- Prevents cross-user session access

### Authentication

- Optional bcrypt password on management WebSocket
- Max auth attempts limit
- Per-connection tracking

## Cross-Platform PTY

| Platform | Implementation |
|----------|----------------|
| Windows | `pywinpty` library |
| Linux/macOS | Standard `pty` module |

Shell detection uses platform-specific methods (registry on Windows, `/etc/shells` on Unix).

## Frontend Architecture

Backend-driven UI - server maintains canonical state, frontend renders reactively.

**Service Layer**:

| Service | Purpose |
|---------|---------|
| `ConfigService` | Fetches `/api/config` (shells, buttons) |
| `ManagementService` | Control plane WebSocket |
| `ConnectionService` | Data plane WebSocket, reconnection logic |
| `TabService` | Renders server-provided tab state |

**Input Handling**:
- `KeyMapper`: Browser keys → terminal sequences
- `ModifierManager`: Ctrl/Alt/Shift with sticky/locked modes
- `GestureRecognizer`: Touch swipe → arrow keys

**State Flow**:
1. Server sends `tab_state_sync` on connect
2. Frontend renders tabs from server state
3. User actions send requests to management WebSocket
4. Server broadcasts `tab_state_update` to all connections
5. All frontends update reactively
