# Agensi Marketplace Listing: CtxDock

## Listing details

- **Name**: CtxDock
- **Summary**: Local, selective project memory for coding agents. Save decisions, fixes, constraints, and handoffs, then retrieve only relevant context across sessions.
- **Price**: Free
- **Requires**:
  - Python 3.11+
  - SQLite with FTS5
  - Agent with terminal and local filesystem access
- **Optional**:
  - Git for automatic repository detection

## Permissions

- **Terminal / Shell**: enabled
- **Read Files**: enabled
- **Write Files**: enabled
- **Environment Variables**: enabled
- **Browser**: disabled
- **Network Access**: disabled
- **Connected services**: none

## File scopes

- `~/.ctxdock/**`
- `${CTXDOCK_HOME}/**`

## Compatibility note

Requires Python 3.11+ with SQLite FTS5 and an agent permitted to run shell commands and write local user storage. Codex is verified. Claude Code, Cursor, Gemini CLI, and VS Code Copilot support remains experimental.

## Documentation link

https://github.com/TheLastAdmiraL/CtxDock
