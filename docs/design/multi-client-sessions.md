# Multi-Client Session Support and Cross-Browser Tab Synchronization

## 1. Executive Summary

This design document outlines the implementation of multi-client session support for Porterminal, enabling multiple browser tabs or devices to connect to the same terminal session simultaneously. The solution addresses three core requirements:

1. **Shared PTY Sessions**: Multiple clients can connect to and interact with a single PTY process
2. **Output Broadcasting**: Terminal output is broadcast to all connected clients in real-time
3. **Tab Synchronization**: Browser tabs stay synchronized with server-side session state

### Design Philosophy: Simplicity for a Small Project

Rather than introducing a new `SessionConnectionRegistry` class, this design keeps connection tracking **inline within `TerminalService`**. This reduces:
- New files: 0 (vs 1)
- New classes: 0 (vs 2)
- Lines of code: ~80 (vs ~300)

The tradeoff is less formal separation of concerns, but for a personal-use project, this is acceptable.

---

## 2. Architecture Overview (Simplified)

### High-Level Design

```
┌──────────────┐                    ┌─────────────────────────────────────────────────────────┐
│   Client A   │◄───WebSocket───────┤                      Server                              │
│  (Browser 1) │                    │                                                          │
└──────────────┘                    │  ┌──────────────────────────────────────────────────┐   │
                                    │  │              TerminalService                      │   │
┌──────────────┐                    │  │                                                   │   │
│   Client B   │◄───WebSocket───────┤  │  _session_connections = {                        │   │
│  (Browser 2) │                    │  │      "abc123": {conn1, conn2, conn3},            │   │
└──────────────┘                    │  │      "def456": {conn4},                          │   │
                                    │  │  }                                                │   │
┌──────────────┐                    │  │                                                   │   │
│   Client C   │◄───WebSocket───────┤  │  _session_read_tasks = {                         │   │
│  (Mobile)    │                    │  │      "abc123": Task (reads PTY, broadcasts),     │───┼──► PTY Processes
└──────────────┘                    │  │      "def456": Task,                             │   │
                                    │  │  }                                                │   │
                                    │  └──────────────────────────────────────────────────┘   │
                                    └─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Inline connection tracking in TerminalService | No new classes needed; keeps codebase small |
| Single PTY read loop per session | Avoids duplicate reads; ensures consistent output ordering |
| Input from any client goes to same PTY | True multiplexing; all clients see each other's input |
| Binary output broadcasting | PTY output is raw bytes; JSON wrapping would break terminal sequences |
| First/last client lifecycle | Clean resource management without separate cleanup timers |

---

## 3. Component Changes (Backend)

### 3.1 Modified: TerminalService (Inline Connection Tracking)

**File**: `porterminal/application/services/terminal_service.py`

Instead of a separate registry class, add two dictionaries directly to TerminalService:

```python
class TerminalService:
    def __init__(self, ...):
        # ... existing init ...

        # Multi-client support: track connections and read loops per session
        self._session_connections: dict[str, set[ConnectionPort]] = {}
        self._session_read_tasks: dict[str, asyncio.Task] = {}
```

**Helper methods** (add to TerminalService):

```python
def _register_connection(self, session_id: str, connection: ConnectionPort) -> int:
    """Register a connection for a session. Returns connection count."""
    if session_id not in self._session_connections:
        self._session_connections[session_id] = set()
    self._session_connections[session_id].add(connection)
    return len(self._session_connections[session_id])

def _unregister_connection(self, session_id: str, connection: ConnectionPort) -> int:
    """Unregister a connection. Returns remaining count."""
    if session_id not in self._session_connections:
        return 0
    self._session_connections[session_id].discard(connection)
    count = len(self._session_connections[session_id])
    if count == 0:
        del self._session_connections[session_id]
        self._session_read_tasks.pop(session_id, None)
    return count

async def _broadcast_output(self, session_id: str, data: bytes) -> None:
    """Broadcast PTY output to all connections for a session."""
    connections = self._session_connections.get(session_id, set())
    dead = []
    for conn in connections:
        try:
            await conn.send_output(data)
        except Exception:
            dead.append(conn)
    for conn in dead:
        connections.discard(conn)

async def _broadcast_message(self, session_id: str, message: dict) -> None:
    """Broadcast JSON message to all connections for a session."""
    connections = self._session_connections.get(session_id, set())
    dead = []
    for conn in connections:
        try:
            await conn.send_message(message)
        except Exception:
            dead.append(conn)
    for conn in dead:
        connections.discard(conn)
```

This is ~40 lines vs ~130 lines for a separate class, with the same functionality.

### 3.2 Updated handle_session() Method

The existing `handle_session()` method is refactored to:
1. Register/unregister the connection
2. Start the broadcast read loop if first client
3. Stop the read loop if last client leaves

```python
async def handle_session(
    self,
    session: Session[PTYPort],
    connection: ConnectionPort,
    skip_buffer: bool = False,
) -> None:
    """Handle terminal session I/O with multi-client support."""
    session_id = str(session.id)

    # Register this connection
    connection_count = self._register_connection(session_id, connection)
    is_first_client = (connection_count == 1)

    try:
        # First client starts the shared read loop
        if is_first_client:
            self._start_broadcast_read_loop(session, connection)

        # Replay buffer for reconnecting clients (not broadcast)
        if not skip_buffer and not session.output_buffer.is_empty:
            buffered = session.get_buffered_output()
            session.clear_buffer()
            if buffered:
                await connection.send_output(buffered)

        # Start heartbeat for this connection
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(connection))

        try:
            # Handle input from this client
            await self._handle_input_loop(session, connection)
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task

    finally:
        # Unregister this connection
        remaining = self._unregister_connection(session_id, connection)

        # Last client: stop the read loop
        if remaining == 0:
            await self._stop_broadcast_read_loop(session_id)

def _start_broadcast_read_loop(
    self,
    session: Session[PTYPort],
    connection: ConnectionPort,
) -> None:
    """Start the PTY read loop that broadcasts to all clients."""
    session_id = str(session.id)
    if session_id in self._session_read_tasks:
        return  # Already running

    task = asyncio.create_task(
        self._read_pty_broadcast_loop(session, session_id)
    )
    self._session_read_tasks[session_id] = task

async def _stop_broadcast_read_loop(self, session_id: str) -> None:
    """Stop the PTY read loop for a session."""
    task = self._session_read_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

async def _read_pty_broadcast_loop(
    self,
    session: Session[PTYPort],
    session_id: str,
) -> None:
    """Read from PTY and broadcast to all connected clients."""
    # Similar to current _read_pty_loop but uses _broadcast_output
    # instead of sending to a single connection
    ...  # See implementation below
```

### 3.3 app.py WebSocket Handler

**No changes needed** - the existing handler already passes `session` and `connection` to `terminal_service.handle_session()`. The multi-client logic is encapsulated within TerminalService.

---

## 4. Component Changes (Frontend)

### 4.1 TabService Enhancements

**File**: `frontend/src/services/TabService.ts`

```typescript
interface ServerTab {
  session_id: string;
  shell_id: string;
  title: string;
  created_at: number;
}

class TabService {
  // Existing methods...

  /**
   * Create a local tab from server-provided session info.
   * Used when another client creates a tab.
   */
  createTabFromServer(serverTab: ServerTab): Tab {
    // Check for duplicate
    if (this.hasServerTab(serverTab.session_id)) {
      return this.getTabBySessionId(serverTab.session_id)!;
    }

    const tab: Tab = {
      id: this.generateTabId(),
      session_id: serverTab.session_id,
      shell_id: serverTab.shell_id,
      title: serverTab.title,
      isActive: false,
      isConnected: false,
      createdAt: serverTab.created_at,
      isRemote: true,  // Flag to indicate externally created
    };

    this.tabs.push(tab);
    this.emit('tab:created', tab);
    this.persistTabs();

    return tab;
  }

  /**
   * Check if a tab exists for a given server session.
   */
  hasServerTab(session_id: string): boolean {
    return this.tabs.some(t => t.session_id === session_id);
  }

  /**
   * Get tab by session_id.
   */
  getTabBySessionId(session_id: string): Tab | undefined {
    return this.tabs.find(t => t.session_id === session_id);
  }

  /**
   * Reconcile local tabs with server-provided list.
   *
   * - Adds tabs that exist on server but not locally
   * - Marks tabs as stale if they exist locally but not on server
   * - Handles race conditions with timestamps
   */
  reconcileWithServer(serverTabs: ServerTab[]): void {
    const serverSessionIds = new Set(serverTabs.map(t => t.session_id));
    const localSessionIds = new Set(this.tabs.map(t => t.session_id));

    // Add missing tabs from server
    for (const serverTab of serverTabs) {
      if (!localSessionIds.has(serverTab.session_id)) {
        this.createTabFromServer(serverTab);
      }
    }

    // Mark local-only tabs as potentially stale
    for (const tab of this.tabs) {
      if (!serverSessionIds.has(tab.session_id)) {
        // Tab exists locally but not on server
        // Could be: recently closed remotely, or network race
        tab.isStale = true;
        this.emit('tab:stale', tab);
      }
    }
  }
}
```

### 4.2 ConnectionService Message Handlers

**File**: `frontend/src/services/ConnectionService.ts`

```typescript
class ConnectionService {
  // Existing code...

  private setupMessageHandlers(): void {
    // Existing handlers...

    // Tab synchronization handlers
    this.on('tab:list', (data: { tabs: ServerTab[] }) => {
      this.tabService.reconcileWithServer(data.tabs);
    });

    this.on('tab:remote_created', (data: ServerTab) => {
      if (!this.tabService.hasServerTab(data.session_id)) {
        const tab = this.tabService.createTabFromServer(data);
        this.showNotification(`Tab "${tab.title}" opened on another device`);
      }
    });

    this.on('tab:remote_closed', (data: { session_id: string }) => {
      const tab = this.tabService.getTabBySessionId(data.session_id);
      if (tab) {
        // Add visual feedback before removal
        tab.isClosing = true;
        this.tabService.emit('tab:closing', tab);

        // Delay removal for animation
        setTimeout(() => {
          this.tabService.closeTab(tab.id);
        }, 300);
      }
    });
  }
}
```

### 4.3 UI Updates for Remote Tabs

**File**: `frontend/src/ui/TabBar.ts`

```typescript
// Visual indicators for tab states
const tabClasses = {
  remote: 'tab--remote',      // Created by another client
  stale: 'tab--stale',        // May no longer exist on server
  closing: 'tab--closing',    // Being closed remotely (fade out)
  syncing: 'tab--syncing',    // Synchronizing state
};

// Add tooltip for remote tabs
if (tab.isRemote) {
  tabElement.title = 'Opened on another device';
}
```

---

## 5. Data Flow (Multi-Client Scenario)

### Scenario: Two browsers connected to same session

```
Timeline:
─────────────────────────────────────────────────────────────────────────────►

Browser A                    Server                         Browser B
    │                           │                               │
    │   1. Connect (first)      │                               │
    │ ─────────────────────────►│                               │
    │   register() returns 1    │                               │
    │   start_read_loop()       │                               │
    │                           │                               │
    │                           │   2. Connect (second)         │
    │                           │◄─────────────────────────────│
    │                           │   register() returns 2        │
    │                           │   (read loop already running) │
    │                           │                               │
    │                           │   3. Replay buffer to B       │
    │                           │ ─────────────────────────────►│
    │                           │                               │
    │   4. Type "ls"            │                               │
    │ ─────────────────────────►│                               │
    │                           │   write to PTY                │
    │                           │                               │
    │                           │   5. PTY output "ls\n..."     │
    │   broadcast_output()      │   broadcast_output()          │
    │◄─────────────────────────│─────────────────────────────►│
    │                           │                               │
    │                           │   6. Type "pwd"               │
    │                           │◄─────────────────────────────│
    │                           │   write to PTY                │
    │                           │                               │
    │   broadcast_output()      │   7. PTY output "/home\n"     │
    │◄─────────────────────────│─────────────────────────────►│
    │                           │                               │
    │   8. Disconnect           │                               │
    │ ─────────────────────────►│                               │
    │   unregister() returns 1  │                               │
    │   (read loop continues)   │                               │
    │                           │                               │
    │                           │   9. Disconnect (last)        │
    │                           │◄─────────────────────────────│
    │                           │   unregister() returns 0      │
    │                           │   stop_read_loop()            │
    │                           │   (PTY stays alive for        │
    │                           │    reconnection)              │
```

### Message Types

| Type | Direction | Format | Purpose |
|------|-----------|--------|---------|
| PTY Output | Server -> Client | Binary | Terminal data |
| PTY Input | Client -> Server | Binary | User keystrokes |
| resize | Client -> Server | JSON | Terminal dimensions |
| ping/pong | Bidirectional | JSON | Connection keepalive |
| tab:list | Server -> Client | JSON | Full tab list sync |
| tab:remote_created | Server -> Client | JSON | New tab notification |
| tab:remote_closed | Server -> Client | JSON | Tab closed notification |
| session_info | Server -> Client | JSON | Session metadata |

---

## 6. Implementation Order (Simplified)

### Phase 1: Backend Multi-Client Support

1. **Update TerminalService**
   - Add `_session_connections` and `_session_read_tasks` dicts
   - Add helper methods: `_register_connection`, `_unregister_connection`, `_broadcast_output`
   - Refactor `handle_session()` to start/stop broadcast loop based on client count
   - Create `_read_pty_broadcast_loop()` that broadcasts to all connections

### Phase 2: Frontend Tab Sync

2. **Update TabService message handlers**
   - Handle `tab:list` - reconcile local tabs with server
   - Handle `tab:remote_created` - create local tab for remote session
   - Handle `tab:remote_closed` - close local tab

### Phase 3: Testing

3. **Manual Testing**
   - Open same session in two browser tabs
   - Verify output appears in both
   - Verify input from either tab works
   - Test reconnection with buffer replay

---

## 7. Testing Strategy

### Unit Tests

```python
# test_session_connection_registry.py

class TestSessionConnectionRegistry:
    async def test_register_first_client_returns_one(self):
        registry = SessionConnectionRegistry()
        ws = MockWebSocket()
        count = await registry.register("session1", ws)
        assert count == 1

    async def test_register_second_client_returns_two(self):
        registry = SessionConnectionRegistry()
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        await registry.register("session1", ws1)
        count = await registry.register("session1", ws2)
        assert count == 2

    async def test_unregister_last_client_returns_zero(self):
        registry = SessionConnectionRegistry()
        ws = MockWebSocket()
        await registry.register("session1", ws)
        count = await registry.unregister("session1", ws)
        assert count == 0

    async def test_broadcast_output_sends_to_all_clients(self):
        registry = SessionConnectionRegistry()
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        await registry.register("session1", ws1)
        await registry.register("session1", ws2)

        await registry.broadcast_output("session1", b"hello")

        assert ws1.sent_bytes == [b"hello"]
        assert ws2.sent_bytes == [b"hello"]

    async def test_broadcast_removes_dead_connections(self):
        registry = SessionConnectionRegistry()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket(raise_on_send=True)
        await registry.register("session1", ws1)
        await registry.register("session1", ws2)

        await registry.broadcast_output("session1", b"hello")

        assert len(registry.get_connections("session1")) == 1

    async def test_concurrent_register_unregister(self):
        """Verify thread safety under concurrent operations."""
        registry = SessionConnectionRegistry()
        websockets = [MockWebSocket() for _ in range(100)]

        # Concurrent registrations
        await asyncio.gather(*[
            registry.register("session1", ws) for ws in websockets
        ])

        assert len(registry.get_connections("session1")) == 100
```

### Integration Tests

```python
# test_multi_client_integration.py

class TestMultiClientSession:
    async def test_two_clients_receive_same_output(self):
        """Both clients should see PTY output."""
        async with TestClient(app) as client:
            ws1 = await client.websocket_connect("/ws?session_id=test1&shell=bash")
            ws2 = await client.websocket_connect("/ws?session_id=test1&shell=bash")

            # Send input from client 1
            await ws1.send_bytes(b"echo hello\n")

            # Both should receive output
            output1 = await ws1.receive_bytes()
            output2 = await ws2.receive_bytes()

            assert b"hello" in output1
            assert b"hello" in output2

    async def test_second_client_receives_buffer_replay(self):
        """Reconnecting client should get buffered output."""
        async with TestClient(app) as client:
            ws1 = await client.websocket_connect("/ws?session_id=test2&shell=bash")
            await ws1.send_bytes(b"echo buffered\n")
            await ws1.receive_bytes()  # Consume output
            await ws1.close()

            # Reconnect
            ws2 = await client.websocket_connect("/ws?session_id=test2")
            replay = await ws2.receive_bytes()

            assert b"buffered" in replay

    async def test_read_loop_stops_after_last_client(self):
        """Read loop should stop when all clients disconnect."""
        registry = app.state.container.get(SessionConnectionRegistry)

        async with TestClient(app) as client:
            ws = await client.websocket_connect("/ws?session_id=test3&shell=bash")

            # Read loop should be running
            assert registry.get_read_loop_task("test3") is not None

            await ws.close()
            await asyncio.sleep(0.1)  # Allow cleanup

            # Read loop should be stopped
            task = registry.get_read_loop_task("test3")
            assert task is None or task.done()
```

### Frontend Tests

```typescript
// TabService.test.ts

describe('TabService', () => {
  describe('createTabFromServer', () => {
    it('creates tab with server-provided data', () => {
      const service = new TabService();
      const serverTab = {
        session_id: 'abc123',
        shell_id: 'bash',
        title: 'Remote Tab',
        created_at: Date.now(),
      };

      const tab = service.createTabFromServer(serverTab);

      expect(tab.session_id).toBe('abc123');
      expect(tab.isRemote).toBe(true);
    });

    it('returns existing tab if duplicate', () => {
      const service = new TabService();
      const serverTab = { session_id: 'abc123', shell_id: 'bash', title: 'Tab', created_at: Date.now() };

      const tab1 = service.createTabFromServer(serverTab);
      const tab2 = service.createTabFromServer(serverTab);

      expect(tab1.id).toBe(tab2.id);
      expect(service.getTabs().length).toBe(1);
    });
  });

  describe('reconcileWithServer', () => {
    it('adds missing tabs from server', () => {
      const service = new TabService();
      service.reconcileWithServer([
        { session_id: 'a', shell_id: 'bash', title: 'Tab A', created_at: 1 },
        { session_id: 'b', shell_id: 'bash', title: 'Tab B', created_at: 2 },
      ]);

      expect(service.getTabs().length).toBe(2);
    });

    it('marks local-only tabs as stale', () => {
      const service = new TabService();
      service.createTab('bash');  // Local tab

      service.reconcileWithServer([]);  // Server has no tabs

      const tab = service.getTabs()[0];
      expect(tab.isStale).toBe(true);
    });
  });
});
```

### Manual Testing Checklist

- [ ] Open same session in two browser windows
- [ ] Type in window A, verify output appears in both windows
- [ ] Type in window B, verify output appears in both windows
- [ ] Close window A, verify window B still works
- [ ] Reconnect window A, verify buffer replay works
- [ ] Create tab in window A, verify it appears in window B
- [ ] Close tab in window A, verify it closes in window B (with animation)
- [ ] Disconnect network on window A, verify reconnection works
- [ ] Open session on mobile device, verify sync with desktop

---

## Appendix: File Changes Summary (Simplified)

| File | Change Type | Description |
|------|-------------|-------------|
| `porterminal/application/services/terminal_service.py` | Modified | Add connection tracking and broadcast loop |
| `frontend/src/services/TabService.ts` | Modified | Add tab sync message handlers |

**Total: 2 files** (vs 7 in the original design)
