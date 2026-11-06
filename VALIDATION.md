# Validation — Git Insights Python Dashboard v0.2.0

**Scope:** validation evidence for the v0.2.0 application package before its import into GitHub. This document does not certify a GitHub Actions run, a live Streamlit browser session, or Windows execution.

**Frozen baseline:** v0.1.0 ZIP SHA-256 `0f3c1eb59c570bae63c563e15a76f7d102e9eb5b8eaf70fc0c70ac93c61c9235`.

**Acceptance:** replace repeated URL paste/checkbox confirmation with GitHub CLI discovery and multi-selection; retain existing local/GitHub manual flows and read-only Git analytics; distinguish file renames/moves from line changes; flag potential identifier-only edits without asserting semantic or productivity equivalence; preserve catalogue compatibility and offline-by-default behavior.

## Executed checks

- `[passed]` Existing baseline, before changes: `python -m pytest -q` → **18 passed**.
- `[passed]` Red state: newly authored GitHub picker and change-quality tests failed import (features absent), before implementation.
- `[passed]` Candidate: `python -m pytest -q` → **27 passed**. Includes original 18 and 9 new tests: GitHub CLI account discovery with pagination-shaped output, malformed/credential-bearing input rejection, delegated Git credential helper command, persisted auth metadata, move-aware Git diffs on real temporary repository, whitespace and identifier candidate detection, folder scoping, explicit UI action gating through a headless test double.
- `[passed]` Python compilation: `python -m compileall -q app.py gitinsights scripts tests`.
- `[passed]` Real local Git test fixture: pure file move with `R100` reports zero rename-aware churn, whitespace formatting reports zero `-w` churn, consistent identifier substitution is flagged as candidate, and code-logic addition remains in adjusted churn.
- `[not run]` Live `gh api`, GitHub private clone/fetch, OAuth/SSO: `gh` is not installed in this sandbox and no account credentials were requested.
- `[not run]` Streamlit actual server startup, AppTest or browser visual verification: `streamlit` is not installed; package installer could not resolve it in the configured sandbox index.
- `[not run]` Windows PowerShell/CMD execution on Windows (scripts preserved).

## Security and measurement limits

- GitHub account discovery and clone/fetch are **two separate, explicit actions**. Selecting a repository and clicking **Adicionar** starts bare mirror cloning without a redundant per-repository confirmation.
- `gh` authentication is delegated to an invocation-scoped Git credential helper; the app does not read, serialize, log or embed auth tokens. Private mirror history is copied to app-owned local storage and is not encrypted by this application.
- Remote URLs are validated against credential-free `github.com` URLs before clone. GitHub Enterprise domains are not enabled.
- No background fetch, scan of other accounts, deletion of existing repositories, or server-side repository changes were introduced.
- **Never interpret line-count metrics as individual productivity.** `-M` applies Git's similarity heuristic; `-w` can hide semantically important Python indent changes. Identifier-only candidates use lexical matching, not compilation or behavioral verification.
- Deep analysis deliberately samples at most 500 filtered commits per explicit run and exposes exact coverage. GitHub picker imports at most 25 repositories per click.

## Reproduce after installing dependencies

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app.py gitinsights scripts tests
python -m streamlit run app.py
```

GitHub CLI flow requires installed and authenticated `gh` (`gh auth status`; `gh auth login` if needed). The first two commands do not call external GitHub APIs as part of the repository test suite.
