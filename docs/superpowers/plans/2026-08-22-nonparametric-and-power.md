# Nonparametric Methods and Power Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute real Mann–Whitney U, Wilcoxon signed-rank, Kruskal–Wallis (+ Dunn/Holm post-hoc), and Spearman correlation analyses, and add a deterministic power/sample-size module — without changing the offline Electron + local Python architecture, the privacy model, or the audit trail.

**Architecture:** The four rank-based methods become verified executors in `analyses.py` and stop being metadata-only. Users reach them through the existing plan-generation flow: `POST /v1/plans` accepts optional per-item `method_overrides`, the planner regenerates the plan with the documented alternative as the selected method, and the standard revision/digest approval flow re-applies. The power module is a stateless loopback endpoint (`POST /v1/power`) backed by a new `power.py` module (statsmodels closed-form solvers); it touches no patient data and therefore lives outside project state. Reporting/visuals treat the new methods as first-class: bilingual narrative, results table, distribution figures, and a Dunn post-hoc table.

**Tech Stack:** Python 3.12 (`.venv-py312`), scipy/statsmodels/pandas, FastAPI, python-docx, matplotlib; React 19 + TypeScript + Vitest for the desktop shell.

**Spec:** User directive (2026-08-22): preserve the BioStat Studio architecture; extend analysis capacity only. Priority: real Mann–Whitney U, Wilcoxon signed-rank, Kruskal–Wallis + appropriate post-hoc/multiple-comparison correction, Spearman correlation, and a power/sample-size module. For every method add tests, assumption/warning handling, table–figure output, and English/Turkish Word results output. Do not break the offline Electron + local Python service architecture, privacy, or the audit log. (Survival, mixed models, and an explicitly exploratory ML module are a later phase — out of scope here.)

## Global Constraints

- Python venv: `services/analysis/.venv-py312` — all Python commands run through it.
- Full Python suite: `services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests` from repo root.
- Desktop tests: `npm run test --workspace apps/desktop`; typecheck `npm run typecheck --workspace apps/desktop`.
- Every executor is deterministic: no RNG, stable orderings (`_levels` descending / ordered-categorical semantics), `random_seed=None`.
- Error contract: value-free `AnalysisExecutionError` codes (snake_case, no data values).
- All p-values validated via `_p_value`; all published floats via `_safe_float` / `_validate_finite_payload`.
- Report text: journal-neutral EN/TR pairs for every new label; no raw diagnostics leak into DOCX except through allowlisted renderers.
- Estimate direction convention: `first_ordered_exposure_level_minus_second_ordered_exposure_level` (matches Welch/paired executors).
- CONFIDENCE_LEVEL = 0.95 throughout; power module defaults alpha=0.05, power=0.80.
- Commits: conventional prefixes (`feat:`, `test:`, `docs:`), no Codex references.

## Method Design Decisions (locked)

**mann_whitney_u** — outcome + 2-level exposure, complete case, per-group n ≥ 2.
- p-value: `scipy.stats.mannwhitneyu(first, second, alternative="two-sided", method=…)`; `method="exact"` iff no ties across pooled values and both group sizes ≤ 25, else `"asymptotic"` (continuity + tie correction). The chosen method is recorded in diagnostics.
- Estimate: Hodges–Lehmann shift = median of all pairwise differences (first − second).
- 95% CI: Campbell–Gardner order-statistic bounds: `K = round(n1*n2/2 − z0.975*sqrt(n1*n2*(n1+n2+1)/12))`, clamped to ≥ 1 (clamping adds warning `nonparametric_ci_extreme_bounds`); CI = (D(K), D(n1·n2+1−K)) over sorted pairwise differences.
- Effect size: rank-biserial `r = 2*U1/(n1*n2) − 1` (U1 = first group's U).
- Guards: zero pooled range → `insufficient_variation`.

**wilcoxon_signed_rank** — outcome + 2-level condition + pair id (same structure validation as paired t; shared helper `_paired_measurements`).
- Differences d = first − second per pair; zero differences dropped (`zero_method="wilcox"`), count recorded; if any dropped, warning `zero_differences_dropped`. All-zero → `insufficient_variation`.
- p-value: `scipy.stats.wilcoxon(nonzero_d, alternative="two-sided", method=…)`; `"exact"` iff no ties in |d| and no zeros dropped and n_nonzero ≤ 25, else `"approx"` with `correction=True`.
- Estimate: pseudomedian = median of Walsh averages of nonzero differences.
- 95% CI: `K = round(m/2 − z0.975*sqrt(n(n+1)(2n+1)/24))` over m = n(n+1)/2 sorted Walsh averages, clamp ≥ 1 with `nonparametric_ci_extreme_bounds`.
- Effect size: matched-pairs rank-biserial `r = (T+ − T−)/(T+ + T−)`.
- `result.n` = number of complete pairs (keeps figure count validation `result.n == used//2`); diagnostics record `pairs_used_for_test`.

**kruskal_wallis** — outcome + exposure with ≥ 3 levels, per-group n ≥ 2.
- Omnibus: `scipy.stats.kruskal(*groups)`; all-identical values → `insufficient_variation`.
- Effect size (and estimate): epsilon-squared `ε² = (H − k + 1)/(n − k)`; CI None/None with `confidence_interval_method: "not_available_rank_epsilon_squared"`.
- Post-hoc: Dunn pairwise z with tie-corrected variance `σ² = (N(N+1)/12 − Σ(t³−t)/(12(N−1)))·(1/ni + 1/nj)` over pooled mid-ranks, two-sided normal p, Holm adjustment via `statsmodels.stats.multitest.multipletests(method="holm")`. Stored in `diagnostics["posthoc"]` as `{"method": "dunn", "adjustment": "holm", "comparisons": [{"first", "second", "rank_mean_difference", "z", "p_value", "p_adjusted"}]}` (level labels as strings — same exposure labels the figures already show).
- Warning `posthoc_with_nonsignificant_omnibus` when omnibus p ≥ 0.05.
- Plan item `multiplicity_strategy = "dunn_pairwise_holm_adjusted"`.

**spearman_rank** — two numeric variables, n ≥ 4, nonzero range each.
- `scipy.stats.spearmanr`; estimate/effect = rho (`spearman_rho`).
- 95% CI: Fisher z with Fieller–Hartley–Pearson SE `1.03/sqrt(n−3)` (documented in diagnostics as `confidence_interval_method: "fisher_z_fieller_se"`).

**Method selection flow** — planner keeps choosing the parametric primary; `build_plan(..., method_overrides={item_id: method})` swaps a plan item to its documented alternative (only `item.method` or `item.robust_alternative` accepted; anything else → blocking error `invalid_method_override:{item_id}`). After a swap the parametric method becomes the item's `robust_alternative` (documented alternative), and estimand/rationale/assumptions/outputs come from the new method's contract. `PlanChoice("pearson_or_spearman")` gains `robust_alternative="spearman_rank"`; `study_model.VERTICAL_SLICE_METHOD_IDS` gains `"spearman_rank"`. `ALTERNATIVE_METADATA_ONLY` becomes empty (methods now verified); the `unverified_selected_method` gate stays for any future metadata-only additions.

**Power module** — `services/analysis/biostat_service/power.py`, endpoint `POST /v1/power` (session-authed, loopback, stateless — no project, no patient data, audit posture unchanged).
- Analyses: `two_sample_t` (Cohen d, TTestIndPower, ratio), `paired_t` (dz, TTestPower), `one_way_anova` (Cohen f, FTestAnovaPower, k groups), `two_proportions` (p1/p2 → `proportion_effectsize` + NormalIndPower), `correlation` (Fisher-z closed form: `n = ((z_{α/2}+z_{power})/atanh(r))² + 3`).
- `solve_for`: `"power"` (given n) or `"sample_size"` (given target power); sample sizes reported both raw and ceiled per group.
- Validation: 0 < alpha < 1, 0 < power < 1, effect sizes finite and > 0 (|r| < 1 and ≠ 0; p1 ≠ p2 in (0,1)), n ≥ 2, ratio > 0, groups ≥ 2; violations → 422 with stable codes.

**Reporting** — METHOD_LABELS/EFFECT_LABELS EN+TR for all four methods; `REPORT_FIGURE_METHODS` and visuals `GROUP_METHODS` gain the three group methods; paired-figure branches accept `wilcoxon_signed_rank`; new Dunn post-hoc DOCX table (validated, 4 columns: comparison, z, p, adjusted p; widths 4560/1600/1600/1600 = 9360) with EN/TR captions; WARNING_CATALOG entries for `zero_differences_dropped`, `nonparametric_ci_extreme_bounds`, `posthoc_with_nonsignificant_omnibus` in both languages.

**Desktop** — PlanReview gains a per-item "use documented alternative" action that regenerates the plan with `method_overrides` (new approval required — existing revision/digest flow untouched); a new Power module panel (form + results, EN/TR) available from the sidebar without a project; types/client extended; tests updated.

## Pinned Reference Values (computed independently 2026-08-22, scipy 1.x/.venv-py312)

MWU: first level "B" = [1.1, 2.3, 2.9, 3.6, 4.5, 5.1], second "A" = [0.8, 1.4, 1.9, 2.2, 2.5] → U1=25, exact p=0.08225108225108226, HL=1.5, CI=(−0.3, 3.2) (K=4), r_rb=0.6666666666666667.

Wilcoxon: pre=[12.0, 11.2, 14.5, 9.0, 13.0, 10.5, 12.4, 11.5, 15.0], post=[10.1, 11.9, 12.1, 8.6, 10.4, 10.0, 11.0, 10.0, 12.2] (first level = "pre" under descending sort) → d has no zeros/ties, W=3, exact p=0.01953125, pseudomedian=1.5, CI=(0.4, 2.4) (K=6), r_rb=0.8666666666666667.

Kruskal (levels C>B>A): C=[7.1, 8.4, 9.2, 6.8, 7.7], B=[5.9, 6.3, 7.0, 6.1], A=[4.2, 5.1, 4.8, 5.5, 4.9] → H=11.082857142857144, p=0.003920921519003687, ε²=0.8257142857142857; Dunn z: C–B 1.4432107063270918 (p .1489611244738834), C–A 3.3260873624811995 (p .0008807431907417271), B–A 1.692654532112021 (p .09052124460534798); Holm-adjusted: [0.18104249, 0.00264223, 0.18104249] (exact: 0.1810424892…, 0.0026422295722251813…, 0.1810424892…).

Spearman: x=1..8, y=[2.1, 1.8, 3.5, 3.9, 5.2, 4.8, 6.9, 7.4] → rho=0.9523809523809524, p=0.00026040002438725105, CI=(0.741574098598738, 0.9920139764772767).

---

### Task 1: Mann–Whitney U executor
**Files:** Modify `services/analysis/biostat_service/analyses.py`; Test `services/analysis/tests/test_analyses_reference.py`.
**Produces:** `run_mann_whitney(frame, item, context) -> AnalysisResult`, registered as `METHODS["mann_whitney_u"]`; effect name `rank_biserial_r`; diagnostics keys `counts, group_sizes, u_statistic, p_value_method, tie_correction_applied, exposure_level_order, estimate_direction, confidence_interval_method`.
- [x] Failing reference test (values above) + guards (insufficient group, zero variation)
- [x] Implement; run; commit

### Task 2: Wilcoxon signed-rank executor
**Files:** Modify `analyses.py` (extract `_paired_measurements` shared with `run_paired_t`); Test as Task 1.
**Produces:** `run_wilcoxon_signed_rank`, `METHODS["wilcoxon_signed_rank"]`; effect `matched_rank_biserial_r`; diagnostics `counts, pairs, pairs_used_for_test, zero_differences_dropped, w_statistic, p_value_method, exposure_level_order, estimate_direction, confidence_interval_method`.
- [x] Failing reference test + zero-difference warning test + all-zero error test
- [x] Implement (refactor `run_paired_t` to share `_paired_measurements`); run full suite; commit

### Task 3: Kruskal–Wallis executor with Dunn/Holm post-hoc
**Files:** Modify `analyses.py`; Test as Task 1.
**Produces:** `run_kruskal_wallis`, `METHODS["kruskal_wallis"]`; effect `rank_epsilon_squared`; diagnostics `counts, group_sizes, h_statistic, degrees_freedom, exposure_level_order, posthoc{…}`, warning rule for nonsignificant omnibus.
- [x] Failing reference test incl. Dunn table + Holm values; nonsignificant-omnibus warning test
- [x] Implement; run; commit

### Task 4: Spearman executor
**Files:** Modify `analyses.py`; Test as Task 1.
**Produces:** `run_spearman`, `METHODS["spearman_rank"]`; effect `spearman_rho`.
- [x] Failing reference test + insufficient-n guard
- [x] Implement; run; commit

### Task 5: Execution gate + study model + planner overrides
**Files:** Modify `analyses.py` (`ALTERNATIVE_METADATA_ONLY = frozenset()`), `study_model.py` (+`spearman_rank`), `planner.py` (contracts for 4 methods, `build_plan(..., method_overrides)`, Pearson choice gains alternative); Tests `test_planner.py`, `test_analyses_reference.py` updates.
**Produces:** `build_plan(brief, profile, roles, method_overrides: dict[str, str] | None = None)`; blocking error `invalid_method_override:{item_id}`; swapped items carry the parametric method as `robust_alternative` and `multiplicity_strategy="dunn_pairwise_holm_adjusted"` for kruskal.
- [x] Failing planner tests: override to alternative per rule; invalid override blocks; pearson→spearman alternative
- [x] Implement; update stale assertions (metadata-only tests); run; commit

### Task 6: Plan endpoint overrides
**Files:** Modify `app.py` (`PlanRequest.method_overrides: dict[str,str] = {}` → `build_plan`, audit event records override ids/methods); Test `test_service_security.py` or plan endpoint tests.
- [x] Failing endpoint test: create plan with override → plan item method swapped, approval + job runs nonparametric end-to-end
- [x] Implement; run; commit

### Task 7: Power module + endpoint
**Files:** Create `services/analysis/biostat_service/power.py`; Modify `app.py` (POST `/v1/power`); Test `services/analysis/tests/test_power.py`.
**Produces:** `compute_power(request: PowerRequest) -> PowerResult` (pydantic models in `power.py`), endpoint returning `{analysis, solve_for, inputs…, power, sample_size…, library_versions}`.
Pinned: two_sample_t d=0.5 α=0.05 power=0.80 → n1=63.76561177540974 (ceil 64); power at n=64/group=0.8014596; correlation r=0.5, α=0.05, power=0.80 → n=(1.959964+0.841621)²/atanh(0.5)²+3=29.0…→30 (verify exact in test via formula); anova f=0.25 k=3 n_total solve; proportions p1=0.6,p2=0.4.
- [x] Failing unit tests per analysis type + validation errors; endpoint test (session auth, stateless)
- [x] Implement; run; commit

### Task 8: Visuals for rank methods
**Files:** Modify `visuals.py` (`GROUP_METHODS` + 3 methods; paired branch accepts `wilcoxon_signed_rank`); Test `test_visuals.py`.
- [x] Failing tests: kruskal figure produced (3 groups), wilcoxon paired figure with pair lines
- [x] Implement; run; commit

### Task 9: Reporting for rank methods + post-hoc table
**Files:** Modify `reporting.py` (labels EN/TR, figure methods, `_report_figure_prose` paired branch, `_add_posthoc_table`, WARNING_CATALOG); Tests `test_reporting.py`, `test_reporting_parity.py`.
- [x] Failing tests: DOCX renders each new method narrative+table row EN/TR; kruskal DOCX contains Dunn table with Holm caption; new warnings render; parity holds
- [x] Implement; run; commit

### Task 10: Desktop — plan override UI + power panel
**Files:** Modify `apps/desktop/src/api/types.ts`, `api/client.ts`, `features/plan/PlanReview.tsx`, `App.tsx`, `features/project/store.ts` (if plan regeneration state), `styles/clinical-calm.css`; Create `features/power/PowerPlanner.tsx`; Tests `App.test.tsx` (+ component tests).
- [x] Failing tests: PlanReview shows "alternatifi kullan/use alternative" and triggers createPlan with overrides; PowerPlanner computes via mocked client and renders result EN/TR
- [x] Implement; `npm run test`, `npm run typecheck`; commit

### Task 11: Docs + gates
**Files:** Modify `README.md`, `README.tr.md` (verified scope: 4 methods now executed, power module; alternatives wording), project note.
- [x] Update scope text EN/TR
- [x] Full gates: Python suite, desktop tests, typecheck, production build; commit

## Self-Review Notes
- Spec coverage: MWU (T1), Wilcoxon (T2), KW+post-hoc (T3), Spearman (T4), selection/assumption flow (T5–6), power module (T7), figures (T8), EN/TR Word output incl. tables (T9), UI (T10), docs (T11). Survival/mixed/ML intentionally out of scope (next phase).
- Privacy/audit: no new persisted patient data; power endpoint stateless; plan override audited through existing `plan_generated` event payload.
- Determinism: no RNG anywhere; all orderings reuse `_levels`/`_sort_key`.
