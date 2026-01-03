# Porterminal Documentation

Web-based terminal accessible from your phone via Cloudflare Quick Tunnel.

## Overview

Porterminal provides a mobile-friendly terminal interface that you can access from any device with a web browser. It uses Cloudflare Quick Tunnels to securely expose your local terminal without port forwarding or firewall configuration.

## Quick Links

- [Installation](installation.md) - Get started with Porterminal
- [Configuration](configuration.md) - Customize your setup
- [Security](security.md) - Password protection & best practices
- [Architecture](architecture.md) - Technical details
- [Development](development.md) - Contributing & release process
- [Changelog](CHANGELOG.md) - Version history

## Key Features

| Feature | Description |
|---------|-------------|
| Mobile UI | Touch-friendly virtual keyboard with modifier keys |
| Multi-tab | Run multiple terminal sessions simultaneously |
| Persistence | Reconnect to running sessions after disconnect |
| Secure | Optional password protection, env vars sanitized |
| Zero-config | Cloudflare tunnel with QR code for instant access |
| Cross-platform | Windows, Linux, and macOS support |

## How It Works

1. **Start** - Run `ptn` from your terminal
2. **Connect** - Scan the QR code with your phone
3. **Use** - Full terminal access with touch-friendly controls

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Phone     │────▶│  Cloudflare  │────▶│   Server    │
│  (Browser)  │◀────│    Tunnel    │◀────│   (Local)   │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Requirements

- Python 3.12+
- cloudflared CLI (auto-installed if missing)
