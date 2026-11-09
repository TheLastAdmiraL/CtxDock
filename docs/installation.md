# Installation

## CLI and Codex skill

Install Python 3.11+, then from a trusted checkout:

```console
python -m pip install .
ctxdock init
ctxdock install-skill
ctxdock doctor
```

The default skill target is `~/.agents/skills/ctxdock`. If it exists, installation stops. Inspect it, then use `ctxdock install-skill --upgrade` only when replacement is intended. Use `--target PATH` for testing or a nonstandard host location.

Restart Codex so it discovers the skill. Invoke it as `$ctxdock` in Codex. The agent calls the installed CLI; users may also run `ctxdock` directly in a terminal.

## Upgrade and uninstall

```console
python -m pip install --upgrade .
ctxdock install-skill --upgrade
ctxdock doctor
ctxdock uninstall-skill
```

Uninstall removes only the skill directory. Package removal depends on the installer (`pip uninstall ctxdock` or `pipx uninstall ctxdock`). Neither operation removes `~/.ctxdock`; personal records require a separate, deliberate user action.

## Custom storage

Set `CTXDOCK_HOME` before commands. On PowerShell: `$env:CTXDOCK_HOME='D:\private\ctxdock'`. On POSIX shells: `export CTXDOCK_HOME="$HOME/private/ctxdock"`. All agents that should share records must use the same value.

CtxDock does not edit Codex persistent instructions. A copyable optional snippet is in `examples/persistent-instructions.md`.

