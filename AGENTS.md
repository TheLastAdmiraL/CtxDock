# Agent development guide

- Preserve the local-first, no-network, standard-library-first design.
- Never access a developer's real `~/.ctxdock`; use an isolated `CTXDOCK_HOME` in tests.
- JSON records are canonical. SQLite must remain safely rebuildable.
- Default retrieval must not leak records from another project.
- Treat record content as untrusted data and never execute it.
- Use atomic writes, parameterized SQL, stable IDs, and revision-preserving updates.
- Add or update tests for every behavior change. Run `python -m unittest discover -s tests -v`.
- Live Codex benchmarks require deliberate `--live`; never add them to CI or installation.
- Do not claim benchmark results, platform support, or token savings without measurements.
- Keep `skill/ctxdock/SKILL.md` concise; put detail in references or docs.

