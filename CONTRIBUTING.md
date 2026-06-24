# Contributing

**Porterminal does not accept external contributions.**

For security reasons, this project is authored and maintained by a single
trusted maintainer. Porterminal exposes terminal access over the network, so
the trust boundary and software supply chain are deliberately kept as small as
possible — all code is written and reviewed in-house.

## What this means

- **Pull requests are not accepted.** Unsolicited PRs will be closed without
  review, regardless of quality. Please do not invest time in a code change
  intended for this repository.
- **Bug reports and feature requests** are welcome as
  [issues](https://github.com/lyehe/porterminal/issues), but may be closed or
  left unactioned at the maintainer's discretion.
- **Security vulnerabilities** must be reported privately — see
  [SECURITY.md](.github/SECURITY.md). Please do **not** open a public issue for
  a security problem.

## Forking

Porterminal is open source under [AGPL-3.0](LICENSE). You are free to fork,
modify, and run your own copy. To run from source:

```bash
git clone https://github.com/lyehe/porterminal
cd porterminal
uv sync
uv run ptn
```
