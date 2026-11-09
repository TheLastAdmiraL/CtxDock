# Contributing

Contributions are welcome. Use Python 3.11 or newer and keep the core dependency-free.

1. Fork and clone the repository.
2. Create a focused branch.
3. Run `python -m pip install -e .`.
4. Run `python -m unittest discover -s tests -v`.
5. For retrieval changes, run `python benchmarks/run_offline.py --sizes 100` and explain meaningful result changes.
6. Open a pull request describing behavior, tests, security/privacy effects, and compatibility.

Tests must set an isolated `CTXDOCK_HOME` or construct `Store` with a temporary directory. Never read or modify a contributor's real `~/.ctxdock`. Do not add network calls to ordinary storage/retrieval. Avoid dependencies unless their benefit clearly outweighs packaging and security costs.

Use small commits, update documentation for user-visible changes, and add a changelog entry. By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

