# BioStat Studio Acceptance Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the five remaining correctness defects, restore a fully green suite, move the packaged sidecar to supported Python 3.12, and prepare the existing vertical slice for operator acceptance without adding features or redesigning the architecture.

**Architecture:** Keep the Electron + React renderer and authenticated loopback FastAPI sidecar. Tighten existing boundaries only: imported projects execute from their immutable workbook snapshot, persisted approvals are verified on reopen, approved variable kinds drive a documented coercion path, cancellation reports the authoritative terminal job, and analysis diagnostics/Excel headers use one canonical vocabulary.

**Tech Stack:** Electron, React, TypeScript, Vitest, Python 3.12, FastAPI, pandas/openpyxl, pytest, PyInstaller, electron-builder.

**Spec:** `docs/superpowers/specs/2026-08-15-biostat-desktop-design.md`

## Global Constraints

- Apple Silicon only; no Intel packaging work.
- Offline-first; renderer receives neither a bearer token nor a raw source path.
- Excel remains the only verified import format.
- Explicit data-role approval and explicit plan approval remain mandatory.
- Reports remain deterministic, journal-neutral, privacy-filtered, and English/Turkish.
- No new statistical methods, importers, signing/notarization, telemetry, or architecture changes.
- Do not merge or push until all automated gates pass and the operator completes the real-workbook GUI acceptance run.

---

### Task 1: Restore the baseline and repository hygiene

**Files:**
- Modify: `services/analysis/tests/test_service_security.py`
- Modify: `.gitignore`
- Create: `scripts/test-all.sh`
- Create: `scripts/tests/test-all.sh`
- Modify: `package.json`
- Delete generated output: `release/mac-arm64/BioStat Studio 2.app`

**Interfaces:**
- Consumes: existing `test:python` and `test:desktop` npm scripts.
- Produces: `npm test` that executes both suites and returns non-zero if either fails.

- [x] Add `monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")` to the restart/reopen test and run that exact test to verify the setup failure is removed.
- [x] Add behavioral shell coverage using a fake `npm` executable: force Python to fail, assert the desktop command still runs, and assert the aggregate script exits non-zero.
- [x] Run the shell test to observe RED because `scripts/test-all.sh` does not exist.
- [x] Implement the minimal aggregate runner with independent exit-code capture and change `package.json` to call it.
- [x] Add explicit `.pytest_cache/` and local `AGENTS.md` ignore rules; retain the local file but never commit it.
- [x] Confirm the current app bundle exists, delete only the stale generated `BioStat Studio 2.app`, and verify exactly one bundle remains.
- [x] Run the focused restart test, shell behavior test, and `git diff --check`.

### Task 2: Execute from the immutable snapshot and verify persisted state

**Files:**
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `services/analysis/tests/test_service_security.py`

**Interfaces:**
- Consumes: `profile_from_manifest(project, manifest)`, `_plan_digest(plan)`, `AnalysisBundle.provenance.data_fingerprint`.
- Produces: fail-closed `_restore_context()` and a new project context whose `profile.source_path` is `<project>/source/source.xlsx`.

- [x] Add an integration test that creates a project, moves/changes the original workbook, and still completes analysis/report generation from the immutable snapshot.
- [x] Run the test to observe RED at `_read_frame()` because the context still points to the external workbook.
- [x] Build the new context from `profile_from_manifest(project, manifest)` immediately after `create_project()`.
- [x] Add tampering tests that alter the stored plan digest, approval binding, completed-job digest, and bundle data fingerprint; each `/v1/projects/open` request must return `422 project_open_failed`.
- [x] Run the tampering tests to observe RED because `_restore_context()` currently trusts stored values.
- [x] Recompute every plan digest on restore, require approval revision/digest equality, require each completed job digest to match its embedded plan, and require bundle provenance to remain internally bound to the persisted result.
- [x] Run all project/service-security persistence tests.

### Task 3: Make approved variable kinds operational

**Files:**
- Modify: `services/analysis/biostat_service/planner.py`
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `services/analysis/tests/test_planner.py`
- Modify: `services/analysis/tests/test_service_security.py`

**Interfaces:**
- Consumes: complete confirmed `dict[str, VariableRole]` and the canonical analysis frame.
- Produces: planner decisions based on `VariableRole.kind` plus deterministic, value-free coercion before execution.

- [x] Add a planner test where inferred `categorical` metadata is explicitly approved as `continuous`; assert the plan uses the approved scientific kind instead of emitting `*_kind_mismatch`.
- [x] Run it to observe RED in `_validate_role()`.
- [x] Replace the inferred-kind equality gate with an approved-kind allowlist gate; append a value-free plan warning when the approved and inferred kinds differ.
- [x] Add service tests for continuous coercion (numeric strings become numeric; non-numeric values become missing and are reflected by existing missing-data handling) and categorical coercion that preserves missingness.
- [x] Run them to observe RED because `_read_frame()` returns untransformed values.
- [x] Add one deterministic `_apply_approved_kinds(frame, roles)` boundary and call it only after fingerprint/header validation. Fail closed for unsupported/date conversions rather than guessing.
- [x] Run planner, service-security, and reference-analysis suites.

### Task 4: Return authoritative cancellation outcomes to the UI

**Files:**
- Modify: `apps/desktop/src/api/client.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/api/client.test.ts`
- Modify: `apps/desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: terminal `JobResponse` from `waitForTerminal(jobId)`.
- Produces: `cancelAnalysis(): Promise<JobResponse | null>`; UI branches on `cancelled`, `completed`, or `failed`.

- [x] Add a client test asserting cancellation returns the terminal completed job when completion wins the race.
- [x] Add an App test asserting that the same race shows completed results and never displays a cancellation notice.
- [x] Run both to observe RED because `cancelAnalysis()` returns `void` and App always clears results.
- [x] Return the authoritative terminal job from the client and make App apply each terminal status explicitly.
- [x] Replace constant 100 ms polling with bounded exponential delays while preserving the existing terminal deadline and progress callbacks.
- [x] Run focused client/App tests, then the complete desktop suite and typecheck.

### Task 5: Map diagnostics emitted by real analysis producers

**Files:**
- Modify: `services/analysis/biostat_service/jobs.py`
- Modify: `services/analysis/tests/test_jobs.py`
- Modify: `services/analysis/tests/test_analyses_reference.py`

**Interfaces:**
- Consumes: `model_fit_failure`, `model_convergence_failure`, and `library_warning` emitted by `analyses.py`.
- Produces: privacy-safe diagnostic categories/codes without exception text or data values.

- [x] Add parameterized job tests using the three real producer codes and literal expected safe categories.
- [x] Run to observe RED because the allowlist currently recognizes different names.
- [x] Extend the allowlist to the actual producer vocabulary while retaining compatibility for existing safe codes.
- [x] Add one integration assertion using the real logistic failure emitted by `analyses.py`.
- [x] Run jobs and reference-analysis suites.

### Task 6: Use canonical Excel column identifiers during execution

**Files:**
- Modify: `services/analysis/biostat_service/data_intake.py`
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `services/analysis/tests/test_data_intake.py`
- Modify: `services/analysis/tests/test_service_security.py`

**Interfaces:**
- Consumes: `variable_key(label)`.
- Produces: `canonicalize_frame_columns(frame)` that renames the actual pandas frame with the same collision-safe keys used by profiling.

- [x] Add a direct data-intake test for numeric `2026`, literal `int:2026`, and literal `str:int:2026` headers; assert three distinct canonical frame columns.
- [x] Add a service integration test that plans and executes against one of those canonical identifiers.
- [x] Run them to observe RED because execution still has raw pandas labels.
- [x] Implement `canonicalize_frame_columns()` with duplicate-key detection and use it in `_read_frame()` before approved-kind coercion.
- [x] Run data-intake, planner, service-security, and reference-analysis suites.

### Task 7: Pin the sidecar build to Python 3.12

**Files:**
- Modify: `scripts/bootstrap-analysis-venv.sh`
- Modify: `scripts/package-macos.sh`
- Modify: `scripts/test-package-bootstrap.sh`
- Create: `scripts/tests/fixtures/bootstrap-python`
- Modify: `README.md`
- Refresh: `services/analysis/requirements.lock` only if Python 3.12 resolution requires a pin change.

**Interfaces:**
- Consumes: an installed `python3.12` executable.
- Produces: a stamped Python 3.12 venv and a Python 3.12 PyInstaller sidecar.

- [x] Check for `python3.12`; if absent, stop and request approval before installing system software.
- [x] Extend the bootstrap behavior test so an unsupported interpreter fails with a clear message and Python 3.12 succeeds.
- [x] Run it to observe RED under the current generic `python3` selection.
- [x] Default `BIOSTAT_BOOTSTRAP_PYTHON` to `python3.12`, assert `3.12.x`, and include interpreter identity in the bootstrap stamp so an old venv cannot be reused.
- [x] Build a fresh isolated Python 3.12 venv; run `pip check`, the Python suite, and sidecar self-test before replacing the packaging input.
- [x] Rebuild the arm64 app/DMG and verify the bundled sidecar reports Python 3.12, passes self-test, and contains no x86_64 slice.

### Task 8: Final automated and operator acceptance gates

**Files:**
- Update: `.superpowers/sdd/2026-08-15-biostat-studio-vertical-slice/progress.md` (ignored execution ledger)
- Update: ErdemOS project note after a durable result.

**Interfaces:**
- Consumes: the completed remediation branch and packaged Apple Silicon artifacts.
- Produces: evidence for merge readiness; it does not itself merge or push.

- [ ] Run Python, desktop, typecheck, production build, `git diff --check`, packaging resource smoke, sidecar self-test, and architecture checks.
- [ ] Run a fresh whole-branch scientific/security review and resolve any load-bearing finding before acceptance.
- [ ] Ask the operator to run one real `.xlsx` through import, complete role approval, plan approval, analysis, cancellation, restart/reopen, and same-job EN/TR DOCX export.
- [ ] Inspect the generated DOCX tables/figures and verify the packaged workflow makes no outbound network connection.
- [ ] Only after those gates, present the three finishing-branch choices. A private remote requires an operator-supplied URL.

## Plan self-review

- Spec coverage: all external-review P0/P1 items except remote/merge are covered; the five final-review correctness findings are covered; Python and real-data gates are explicit. New methods/importers/signing remain excluded.
- Placeholder scan: no TBD/TODO or unspecified implementation step remains.
- Type consistency: `cancelAnalysis()` returns the existing `JobResponse`; profile/execution share `variable_key`; persisted state uses the existing `_plan_digest()` and provenance fingerprint.
