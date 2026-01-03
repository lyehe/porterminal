"""Tests for UserConnectionRegistry."""

from porterminal.domain import UserId

from ..conftest import MockConnection


class TestUserConnectionRegistryLifecycle:
    """Tests for connection registration and unregistration."""

    async def test_register_connection(self, connection_registry, user_id, mock_connection):
        """Test registering a connection."""
        await connection_registry.register(user_id, mock_connection)

        assert connection_registry.connection_count(user_id) == 1

    async def test_register_multiple_same_user(self, connection_registry, user_id):
        """Test registering multiple connections for same user."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        conn3 = MockConnection()

        await connection_registry.register(user_id, conn1)
        await connection_registry.register(user_id, conn2)
        await connection_registry.register(user_id, conn3)

        assert connection_registry.connection_count(user_id) == 3

    async def test_register_multiple_different_users(self, connection_registry):
        """Test registering connections for different users."""
        user1 = UserId("user-1")
        user2 = UserId("user-2")
        conn1 = MockConnection()
        conn2 = MockConnection()

        await connection_registry.register(user1, conn1)
        await connection_registry.register(user2, conn2)

        assert connection_registry.connection_count(user1) == 1
        assert connection_registry.connection_count(user2) == 1
        assert connection_registry.total_connections() == 2

    async def test_unregister_connection(self, connection_registry, user_id, mock_connection):
        """Test unregistering a connection."""
        await connection_registry.register(user_id, mock_connection)

        await connection_registry.unregister(user_id, mock_connection)

        assert connection_registry.connection_count(user_id) == 0

    async def test_unregister_cleans_empty_user(
        self, connection_registry, user_id, mock_connection
    ):
        """Test unregistering last connection cleans up user entry."""
        await connection_registry.register(user_id, mock_connection)
        await connection_registry.unregister(user_id, mock_connection)

        # Internal cleanup: user should no longer be tracked
        assert connection_registry.total_connections() == 0

    async def test_connection_count_accuracy(self, connection_registry, user_id):
        """Test connection_count is accurate after operations."""
        conn1 = MockConnection()
        conn2 = MockConnection()

        assert connection_registry.connection_count(user_id) == 0

        await connection_registry.register(user_id, conn1)
        assert connection_registry.connection_count(user_id) == 1

        await connection_registry.register(user_id, conn2)
        assert connection_registry.connection_count(user_id) == 2

        await connection_registry.unregister(user_id, conn1)
        assert connection_registry.connection_count(user_id) == 1

    async def test_total_connections_across_users(self, connection_registry):
        """Test total_connections counts all users."""
        user1 = UserId("user-1")
        user2 = UserId("user-2")

        await connection_registry.register(user1, MockConnection())
        await connection_registry.register(user1, MockConnection())
        await connection_registry.register(user2, MockConnection())

        assert connection_registry.total_connections() == 3


class TestUserConnectionRegistryBroadcast:
    """Tests for broadcasting messages."""

    async def test_broadcast_returns_count(self, connection_registry, user_id):
        """Test broadcast returns number of successful sends."""
        conn1 = MockConnection()
        conn2 = MockConnection()

        await connection_registry.register(user_id, conn1)
        await connection_registry.register(user_id, conn2)

        count = await connection_registry.broadcast(user_id, {"type": "test"})

        assert count == 2

    async def test_broadcast_all_receive_message(self, connection_registry, user_id):
        """Test all connections receive the broadcast message."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        message = {"type": "tab_created", "tab_id": "123"}

        await connection_registry.register(user_id, conn1)
        await connection_registry.register(user_id, conn2)

        await connection_registry.broadcast(user_id, message)

        assert conn1.sent_messages == [message]
        assert conn2.sent_messages == [message]

    async def test_broadcast_with_exclude_filter(self, connection_registry, user_id):
        """Test broadcast excludes specified connection."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        message = {"type": "sync"}

        await connection_registry.register(user_id, conn1)
        await connection_registry.register(user_id, conn2)

        count = await connection_registry.broadcast(user_id, message, exclude=conn1)

        assert count == 1
        assert len(conn1.sent_messages) == 0
        assert len(conn2.sent_messages) == 1

    async def test_broadcast_empty_user_returns_zero(self, connection_registry, user_id):
        """Test broadcast to user with no connections returns 0."""
        count = await connection_registry.broadcast(user_id, {"type": "test"})

        assert count == 0

    async def test_broadcast_exception_resilience(self, connection_registry, user_id):
        """Test broadcast continues despite individual connection errors."""
        good_conn = MockConnection()
        bad_conn = MockConnection()

        # Make bad_conn raise exception
        async def raise_error(msg):
            raise Exception("Connection failed")

        bad_conn.send_message = raise_error

        await connection_registry.register(user_id, good_conn)
        await connection_registry.register(user_id, bad_conn)

        count = await connection_registry.broadcast(user_id, {"type": "test"})

        # Should count only successful send
        assert count == 1
        assert len(good_conn.sent_messages) == 1

    async def test_broadcast_partial_failure(self, connection_registry, user_id):
        """Test broadcast counts only successful sends."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        conn3 = MockConnection()

        # Make conn2 fail
        async def raise_error(msg):
            raise Exception("Network error")

        conn2.send_message = raise_error

        await connection_registry.register(user_id, conn1)
        await connection_registry.register(user_id, conn2)
        await connection_registry.register(user_id, conn3)

        count = await connection_registry.broadcast(user_id, {"type": "test"})

        assert count == 2  # 2 successful, 1 failed


class TestUserConnectionRegistryEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    async def test_register_after_unregister(self, connection_registry, user_id, mock_connection):
        """Test re-registering after unregistering works."""
        await connection_registry.register(user_id, mock_connection)
        await connection_registry.unregister(user_id, mock_connection)
        await connection_registry.register(user_id, mock_connection)

        assert connection_registry.connection_count(user_id) == 1

    async def test_broadcast_parallel_execution(self, connection_registry, user_id):
        """Test broadcast sends to all connections in parallel."""
        # Create multiple connections
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            await connection_registry.register(user_id, conn)

        message = {"type": "parallel_test"}
        count = await connection_registry.broadcast(user_id, message)

        assert count == 5
        for conn in connections:
            assert conn.sent_messages == [message]

    async def test_unregister_nonexistent_silent(
        self, connection_registry, user_id, mock_connection
    ):
        """Test unregistering non-existent connection is silent."""
        # Should not raise
        await connection_registry.unregister(user_id, mock_connection)

        assert connection_registry.connection_count(user_id) == 0
