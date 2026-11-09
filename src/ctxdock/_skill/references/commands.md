# CtxDock commands

`ctxdock init`; `ctxdock save`; `ctxdock find QUERY`; `ctxdock get ID --summary`; `ctxdock list`; `ctxdock update ID`; `ctxdock handoff`; `ctxdock rebuild`; `ctxdock doctor`; `ctxdock stats`.

JSON input is accepted on stdin. Project search is isolated by default. `--cross-project` crosses that boundary explicitly. Shared records are intentionally visible everywhere. Use `--max-chars` for strict output budgets.
