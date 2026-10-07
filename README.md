<p align="center">
  <img src="https://raw.githubusercontent.com/porterminal/porterminal/master/assets/header.png?v=4" alt="PTN — Portable Terminal" width="800">
</p>

<h1 align="center">Give your agent any computer</h1>

<p align="center">
  One command. One URL. A real terminal for your agent, a live view for you.
</p>

<p align="center">
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/v/ptn?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/ptn/"><img src="https://img.shields.io/pypi/pyversions/ptn?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/porterminal/porterminal/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/porterminal/porterminal/ci.yml?branch=master&style=flat-square&logo=github&label=CI" alt="CI"></a>
  <a href="https://github.com/porterminal/porterminal/blob/master/LICENSE"><img src="https://img.shields.io/github/license/porterminal/porterminal?style=flat-square" alt="License"></a>
</p>

Run Porterminal on a Windows, macOS, or Linux computer and give the generated
link to your AI agent. It gets a real shell with the files, tools, and projects
on that machine. Open the same link on your phone or in any browser to watch
the agent work and type into its terminal.

## Start here

On the computer you want to give your agent:

```bash
uvx ptn
```

1. **Give the agent the link.** Press **`c`** in the local Porterminal window
   to copy the URL and connection instructions. Paste them into your agent
   with a task. The agent needs remote MCP support or a way to make HTTP requests.
2. **Open your view.** Scan the QR code or open the complete URL in a browser.
   Select the agent's **🤖 tab** to see its terminal.
3. **Work together.** Watch the output, answer an interactive prompt, type a
   command, or close the tab to end that shell.

To start in a particular project, use `uvx ptn /path/to/project`.
For installation options, see [installation](https://github.com/porterminal/porterminal/blob/master/docs/installation.md), or use an installer below.

> **The link is the key to the computer.** The complete URL and QR code grant
> shell access. Share them only with people and agents you trust.
> [Read the security model](#security).

## The agent works. You stay in the loop.

| Your agent | You |
|------------|-----|
| Runs commands in the computer's real shell | Watches the same output live in a browser |
| Reads terminal screens and answers prompts | Types into the same terminal when needed |
| Keeps shell state across tool calls | Switches between agent and personal tabs |
| Uses MCP or HTTP to connect | Uses the QR code or URL from a phone or desktop |

Terminal input is shared; coordinate typing with your agent. Porterminal
supports interactive terminal apps, multiple tabs, and reconnecting to running
sessions while the server and session remain alive.

The phone UI includes Ctrl/Alt/Shift keys, touch selection, scrolling,
pinch-to-zoom, and a compose field for editing or dictating longer input.
See [terminal controls](https://github.com/porterminal/porterminal/blob/master/docs/frontend_features.md).

## Try the demo

Give an agent a small invoice project with a failing check. Watch it find the
bug, edit the file, and turn the checks green. Then answer the receipt's label
prompt from your phone and have the agent read the result.

The [demo guide](https://github.com/porterminal/porterminal/blob/master/docs/demo.md) includes a ready-to-copy project, an agent task,
and a 60-second recording plan. It demonstrates commands, file changes,
verification, and human input in one shared session.

## Connect your agent

Pressing **`c`** copies instructions for the available connection methods.
The running server also serves them at `<url>/llms.txt`.

Here, **`<url>` is the complete generated URL, including its access code**.

| Agent capability | Connection |
|------------------|------------|
| Remote MCP | `<url>/mcp` — Streamable HTTP |
| HTTP requests | `<url>/api/agent/run` — REST |
| Browser automation | Open `<url>/`; use **Terminal screen** and **Terminal input** |

MCP exposes four tools: `run_command`, `read_screen`, `send_keys`, and
`send_signal`. REST returns a `session_id` that the agent reuses for subsequent
commands and interaction. Agent shells appear as 🤖 tabs in your browser.

See [agent access](https://github.com/porterminal/porterminal/blob/master/docs/agent-access.md) for client setup, request examples,
session lifetimes, and long-running commands.

## Install

Requires **Python 3.12+**. Porterminal attempts to install `cloudflared`
automatically when it is missing.

| Method | Run or install | Update |
|--------|----------------|--------|
| uvx | `uvx ptn` | `uvx --isolated ptn@latest` |
| uv tool | `uv tool install ptn` | `uv tool upgrade ptn` |
| pipx | `pipx install ptn` | `pipx upgrade ptn` |
| pip | `pip install ptn` | `pip install -U ptn` |

**Install uv and Porterminal together:**

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/porterminal/porterminal/master/install.ps1 | iex"
```

macOS / Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/porterminal/porterminal/master/install.sh | sh
```

## Usage

After installing, run `ptn` or `ptn /path/to/project`.

| Option | Purpose |
|--------|---------|
| `--no-tunnel` | Run without a Cloudflare tunnel |
| `--mcp-only` | Expose MCP only; disables the QR code, browser terminal, and REST API |
| `--compose` | Start with the mobile compose field enabled |
| `--init` | Generate `.ptn/ptn.yaml` with buttons discovered from project scripts |
| `--password` | Add a password to browser terminal access |
| `--help` | Show all options |
| `--version` | Show the installed version |

While running: **`c`** copies the agent instructions, **`u`** copies only the
URL, and **`s`** shows the share text on screen (**`q`** closes it).
**Ctrl+C** stops Porterminal. In MCP-only mode the share keys use the MCP URL.

Custom shells, toolbar buttons, and startup settings live in `ptn.yaml`.
See [configuration](https://github.com/porterminal/porterminal/blob/master/docs/configuration.md).

## Security

Porterminal gives access to a real shell with your user's permissions. The
starting directory is a convenience, not a sandbox or a limit on file access.

Each launch creates a new 128-bit random access path. The bare tunnel hostname
and wrong paths return 404, but anyone with the complete URL can use the shell.
Keep the URL and QR code private, stop Porterminal when finished, and restart
it to rotate the access code if the link leaks.

**The optional password protects browser connections. MCP and REST use the
complete URL as their credential and do not require that password.**

See [security](https://github.com/porterminal/porterminal/blob/master/docs/security.md) for the full model and password behavior.
Report vulnerabilities through [the security policy](https://github.com/porterminal/porterminal/blob/master/.github/SECURITY.md).

## Documentation and development

- [Installation](https://github.com/porterminal/porterminal/blob/master/docs/installation.md)
- [Agent access: MCP, REST, and browser fallback](https://github.com/porterminal/porterminal/blob/master/docs/agent-access.md)
- [Demo setup and recording](https://github.com/porterminal/porterminal/blob/master/docs/demo.md)
- [Configuration](https://github.com/porterminal/porterminal/blob/master/docs/configuration.md)
- [Architecture](https://github.com/porterminal/porterminal/blob/master/docs/architecture.md)
- [Development and release process](https://github.com/porterminal/porterminal/blob/master/docs/development.md)
- [Changelog](https://github.com/porterminal/porterminal/blob/master/docs/CHANGELOG.md)

Bug reports and feature requests are welcome as
[issues](https://github.com/porterminal/porterminal/issues).
External pull requests and code contributions are not accepted; see
[CONTRIBUTING.md](https://github.com/porterminal/porterminal/blob/master/CONTRIBUTING.md). You can fork and run your own copy.

## License

[AGPL-3.0](https://github.com/porterminal/porterminal/blob/master/LICENSE)
