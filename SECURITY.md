# Security policy

## Supported versions

Until the first stable release, only the latest commit on the default branch receives security fixes.

## Reporting a vulnerability

Use GitHub's **Security → Report a vulnerability** flow for this repository when available. Do not open a public issue containing exploit details, private records, or credentials. If private vulnerability reporting is unavailable, contact a repository maintainer through an existing private channel shown on their GitHub profile and provide only enough non-sensitive detail to establish contact.

Include the affected version, operating system, reproduction steps, impact, and suggested mitigation. Remove personal memories and secrets from logs. Maintainers should acknowledge reports, coordinate a fix and disclosure, and credit reporters who want attribution; exact response times are not promised at this pre-release stage.

CtxDock secret detection is defense in depth, not a credential vault. A local user who can read `~/.ctxdock` can read stored knowledge.

