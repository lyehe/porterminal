"""Network utilities for Porterminal."""

import socket


def is_port_available(host: str, port: int) -> bool:
    """Check if host:port is available to bind.

    Args:
        host: Host address to check.
        port: Port number to check.

    Returns:
        True if port is available, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(host: str, preferred_port: int, tries: int = 25) -> int:
    """Find an available port, starting at preferred_port and incrementing.

    Args:
        host: Host address to bind.
        preferred_port: Preferred port to start searching from.
        tries: Number of consecutive ports to try.

    Returns:
        Available port number.
    """
    for offset in range(tries):
        candidate = preferred_port + offset
        if is_port_available(host, candidate):
            return candidate
    # Fallback: ask OS for an ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]
