# CtxDock Agent Installation Playbook

> **Notice for AI Coding Agents (Antigravity, Claude Code, Cursor, OpenAI Codex, Gemini CLI)**:
> When the user asks you to install or set up CtxDock, follow this non-interactive playbook. Do **not** launch interactive terminal prompts. Conduct the setup interview directly with the user in your chat.

---

## Agent Step-by-Step Installation Procedure

### 1. Ask the User the Setup Questions in Chat
Ask the user the following two questions in your conversation:

1. **Storage Scope**:
   * **Project-Specific (Local)** *(Recommended)*:
     Memories are saved directly inside this repository at `.ctxdock/`. They never leave this project, keeping context clean and focused. The JSON records can be committed to Git so every agent and team member shares the same knowledge.
   * **Global**:
     Memories are saved in `~/.ctxdock/` on this machine and can be accessed across all projects and workspaces.

2. **Target Agents**:
   * Which coding agents should have access?
     - `Antigravity`
     - `Claude Code`
     - `Cursor`
     - `OpenAI Codex`
     - `Gemini CLI`
     - `All` (Recommended)

---

### 2. Execute the Headless Installer
Once the user answers, run the non-interactive setup script using your shell tool:

```bash
# Project-specific installation for all agents:
python install.py --mode local --agents all

# Project-specific installation for specific agents:
python install.py --mode local --agents antigravity,cursor,claude

# Global installation across all projects:
python install.py --mode global --agents all
```

The script will automatically:
- Create the target `.ctxdock/` memory store with safe `.gitignore` defaults.
- Place the self-contained standard-library engine (`scripts/ctxdock.py`) and skill instructions into each agent's native discovery folder (`.agent/skills/`, `.cursor/rules/`, `CLAUDE.md`, etc.).
- Require **zero `pip install`** and zero external dependencies.

---

### 3. Confirm Success to the User
Report back:
1. The installation mode (`local` or `global`).
2. The memory directory (`.ctxdock/` or `~/.ctxdock/`).
3. Confirmation of the agent hooks configured.
4. An invitation to test saving their first architecture decision or session handoff.
