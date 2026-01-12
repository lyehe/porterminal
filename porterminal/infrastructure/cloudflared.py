"""Cloudflared installation and management."""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from rich.console import Console

console = Console()


class CloudflaredInstaller:
    """Platform-specific cloudflared installer."""

    @staticmethod
    def _add_to_path(path: str | Path) -> None:
        """Add directory to PATH for current process."""
        path_str = str(path)
        os.environ["PATH"] = path_str + os.pathsep + os.environ.get("PATH", "")
        console.print(f"[dim]Added to PATH: {path_str}[/dim]")

    @staticmethod
    def is_installed() -> bool:
        """Check if cloudflared is installed."""
        return shutil.which("cloudflared") is not None

    @staticmethod
    def install() -> bool:
        """Auto-install cloudflared on the current platform.

        Returns:
            True if installation succeeded, False otherwise.
        """
        console.print("[cyan]Installing cloudflared...[/cyan]")

        if sys.platform == "win32":
            return CloudflaredInstaller._install_windows()
        elif sys.platform == "linux":
            return CloudflaredInstaller._install_linux()
        elif sys.platform == "darwin":
            return CloudflaredInstaller._install_macos()
        else:
            console.print(f"[yellow]Auto-install not supported on {sys.platform}[/yellow]")
            return False

    @staticmethod
    def _find_cloudflared_windows() -> str | None:
        """Find cloudflared.exe in common Windows install locations."""
        common_paths = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "cloudflared",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "cloudflared",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "cloudflared",
            Path(os.environ.get("LOCALAPPDATA", "")) / "cloudflared",
            Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
        ]

        for path in common_paths:
            if not path.exists():
                continue
            # Direct exe in folder
            exe = path / "cloudflared.exe"
            if exe.exists():
                return str(path)
            # Search in subdirectories (for WinGet packages folder)
            for exe in path.rglob("cloudflared.exe"):
                return str(exe.parent)

        return None

    @staticmethod
    def _install_windows() -> bool:
        """Install cloudflared on Windows."""
        # Try winget first (preferred)
        if shutil.which("winget"):
            try:
                result = subprocess.run(
                    [
                        "winget",
                        "install",
                        "--id",
                        "Cloudflare.cloudflared",
                        "-e",
                        "--silent",
                        "--accept-source-agreements",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0 or "already installed" in result.stdout.lower():
                    console.print("[green]✓ Installed via winget[/green]")

                    # Try to find and add to PATH for current session
                    install_path = CloudflaredInstaller._find_cloudflared_windows()
                    if install_path:
                        CloudflaredInstaller._add_to_path(install_path)
                    # Return True regardless - winget succeeded, may just need shell restart
                    return True
            except (subprocess.TimeoutExpired, OSError) as e:
                console.print(f"[dim]winget failed: {e}[/dim]")

        # Fallback: direct download
        try:
            import zipfile

            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.zip"
            install_dir = Path.home() / ".cloudflared" / "bin"
            install_dir.mkdir(parents=True, exist_ok=True)

            console.print("[dim]Downloading from GitHub...[/dim]")

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name
                urllib.request.urlretrieve(url, tmp_path)

            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extractall(install_dir)

            os.unlink(tmp_path)

            exe_path = install_dir / "cloudflared.exe"
            if exe_path.exists():
                CloudflaredInstaller._add_to_path(install_dir)
                console.print(f"[green]✓ Installed to {install_dir}[/green]")
                return True

        except (OSError, urllib.error.URLError) as e:
            console.print(f"[red]Download failed: {e}[/red]")

        return False

    @staticmethod
    def _find_cloudflared_unix() -> str | None:
        """Find cloudflared in common Unix install locations."""
        common_paths = [
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
            Path.home() / ".local" / "bin",
            Path.home() / "bin",
        ]

        for path in common_paths:
            exe = path / "cloudflared"
            if exe.exists() and os.access(exe, os.X_OK):
                return str(path)

        return None

    @staticmethod
    def _install_linux() -> bool:
        """Install cloudflared on Linux."""
        # Determine architecture
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        elif machine.startswith("arm"):
            arch = "arm"
        else:
            arch = "amd64"  # Default fallback

        # Try package managers first
        pkg_managers = [
            (["apt-get", "install", "-y", "cloudflared"], "apt"),
            (["yum", "install", "-y", "cloudflared"], "yum"),
            (["dnf", "install", "-y", "cloudflared"], "dnf"),
        ]

        for cmd, name in pkg_managers:
            if shutil.which(cmd[0]):
                try:
                    # Add Cloudflare repo first for apt
                    if name == "apt":
                        # Use "any" distribution - works on all Debian-based systems
                        # (Ubuntu, Debian, Mint, Pop!_OS, etc.) without codename detection
                        # See: https://pkg.cloudflare.com/
                        subprocess.run(
                            [
                                "bash",
                                "-c",
                                "sudo mkdir -p --mode=0755 /usr/share/keyrings && "
                                "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && "
                                "echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list && "
                                "sudo apt-get update",
                            ],
                            capture_output=True,
                            timeout=60,
                        )
                    result = subprocess.run(
                        ["sudo"] + cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode == 0:
                        console.print(f"[green]✓ Installed via {name}[/green]")

                        # Check if now in PATH
                        if shutil.which("cloudflared"):
                            return True

                        # Try to find and add to PATH
                        install_path = CloudflaredInstaller._find_cloudflared_unix()
                        if install_path:
                            CloudflaredInstaller._add_to_path(install_path)
                        # Return True regardless - package manager succeeded
                        return True
                except (subprocess.TimeoutExpired, OSError) as e:
                    console.print(f"[dim]{name} failed: {e}[/dim]")

        # Fallback: direct binary download
        try:
            url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
            install_dir = Path.home() / ".local" / "bin"
            install_dir.mkdir(parents=True, exist_ok=True)
            bin_path = install_dir / "cloudflared"

            console.print("[dim]Downloading from GitHub...[/dim]")
            urllib.request.urlretrieve(url, bin_path)

            # Make executable
            os.chmod(bin_path, 0o755)

            # Add to PATH for this session
            CloudflaredInstaller._add_to_path(install_dir)
            console.print(f"[green]✓ Installed to {bin_path}[/green]")
            return True

        except (OSError, urllib.error.URLError) as e:
            console.print(f"[red]Download failed: {e}[/red]")

        return False

    @staticmethod
    def _install_macos() -> bool:
        """Install cloudflared on macOS."""
        # Try Homebrew first
        if shutil.which("brew"):
            try:
                result = subprocess.run(
                    ["brew", "install", "cloudflared"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    console.print("[green]✓ Installed via Homebrew[/green]")

                    # Check if now in PATH
                    if shutil.which("cloudflared"):
                        return True

                    # Try to find and add to PATH
                    install_path = CloudflaredInstaller._find_cloudflared_unix()
                    if install_path:
                        CloudflaredInstaller._add_to_path(install_path)
                    # Return True regardless - Homebrew succeeded
                    return True
            except (subprocess.TimeoutExpired, OSError) as e:
                console.print(f"[dim]Homebrew failed: {e}[/dim]")

        # Fallback: direct download
        try:
            import tarfile

            machine = platform.machine().lower()
            arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"

            url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-{arch}.tgz"
            install_dir = Path.home() / ".local" / "bin"
            install_dir.mkdir(parents=True, exist_ok=True)

            console.print("[dim]Downloading from GitHub...[/dim]")

            with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
                tmp_path = tmp.name
                urllib.request.urlretrieve(url, tmp_path)

            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extractall(install_dir)

            os.unlink(tmp_path)

            bin_path = install_dir / "cloudflared"
            if bin_path.exists():
                os.chmod(bin_path, 0o755)
                CloudflaredInstaller._add_to_path(install_dir)
                console.print(f"[green]✓ Installed to {bin_path}[/green]")
                return True

        except (OSError, urllib.error.URLError) as e:
            console.print(f"[red]Download failed: {e}[/red]")

        return False
