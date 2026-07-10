# tests_integration/

Real end-to-end tests that hit real external services (Qualtrics, FollowMee,
the research drive) using real **dev-environment** credentials, loaded
exactly the way the app itself loads them: via the git-ignored `environment`
marker file at the repo root and the drive-sourced `config_base/api/*.api`
files (see `config/README.md`). Nothing here is mocked.

This is deliberately separate from `tests/` and `tests_interface/` (both
fully offline, no network/drive dependency, gated by CI):

- **Not run in CI.** `.github/workflows/tests.yml` has no secrets configured
  and never will for this directory — these tests depend on the research
  drive being mounted and real dev API tokens being filled in, neither of
  which exists in a GitHub Actions runner.
- **Not in `pytest.ini`'s `testpaths`.** A bare `pytest` from the repo root
  will not pick this directory up.
- **Local-only, run manually:**

  ```
  make test-integration
  ```

  (equivalent to `.venv/bin/python -m pytest tests_integration -v`, run from
  the repo root).

## Credentials

Each test loads a real `PRISM` instance (`real_app` fixture in
`conftest.py`) against the real `environment` marker + drive-sourced
`config_base`, then checks whether the credentials it needs are actually
filled in (not still a `"REPLACE_WITH_..."` placeholder value, which is what
the checked-in `.api` templates on the drive ship with before someone fills
in the real dev values). If they aren't, the test calls
`pytest.skip("dev credentials not available: ...")` with the specific
missing/placeholder field names, rather than failing — this directory is
meant to be safe to run (and skip cleanly) on any machine, whether or not
that machine has the research drive mounted and dev credentials populated.

## What's covered

Per the codebase's own "deliberately deferred" list (root `CLAUDE.md`'s
Improvements section, `plan/02-server-pytest.md`) — the real network-calling
paths that `tests/`'s mocked/offline coverage deliberately does not exercise:

- `test_pulldown_qualtrics_data.py` — `PulldownQualtricsData.run()` against
  the real dev Qualtrics survey.
- `test_pulldown_followmee_data.py` — `PulldownFollowmeeData.run()` against
  the real dev FollowMee account.
- `test_environment_files.py` — for **both** `"dev"` and `"prod"` (not just
  whichever the repo's `environment` marker file currently points to;
  `run_prism.py::load_paths()` grew an optional `environment` param so this
  file can pick each one explicitly), checks that every file
  `load_paths()`/`load_api_keys()` expect under that environment's
  `config_base` actually exists, and that the drive-sourced `.api`/CSV files
  are populated beyond their checked-in templates (not still
  `REPLACE_WITH_...` placeholders or empty CSVs with only a header row).
  Unlike the other files here,
  it doesn't use the `real_app` fixture (that always loads whichever single
  environment the marker file points to) and it doesn't call
  `require_real_credentials` — a missing/placeholder-only field here is
  exactly the actionable problem this file exists to catch, not a
  precondition to skip past. It skips per-environment only when that
  environment isn't set up on this machine at all (drive not mounted, or
  `config_base` doesn't exist under it) — see `PLACEHOLDER_PREFIX`/
  `_is_real_value` in `src/_helper.py`, shared with app runtime code and
  imported here via `conftest.py`.
