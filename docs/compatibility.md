# Agent compatibility

CtxDock has two portable layers: the Python CLI and the global on-disk format. Agent discovery and invocation syntax are host-specific.

## Codex

Codex is the initial integration. Install to `~/.agents/skills/ctxdock`, restart, and invoke `$ctxdock`. This repository tests installer behavior and CLI execution; a fresh-session human acceptance test is still recommended before a v1 release.

## Claude Code (experimental)

The same `ctxdock` executable and `CTXDOCK_HOME` can be called from Claude Code. Copy or adapt `skill/ctxdock/SKILL.md` using the current Claude Code skill mechanism and invoke it using that host's native syntax. This path has not been verified and `/ctxdock` is not promised on every version.

## Cursor (experimental)

Cursor agents can call the same CLI if their environment exposes it. Adapt the concise skill instructions to Cursor's current rules/skills feature. Discovery, approval prompts, and slash commands vary by version and remain untested here.

Never point integrations at different homes if they are expected to share knowledge. Do not assume an agent can read conversations or sessions unavailable in its current context and tools.

