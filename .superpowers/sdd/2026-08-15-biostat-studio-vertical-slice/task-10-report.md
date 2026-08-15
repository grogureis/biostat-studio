# Task 10 — Clinical Calm desktop workflow

## Scope

Implemented the renderer-only, six-stage Clinical Calm workflow in `apps/desktop/src`, including the safe API boundary, local project state, bilingual copy, data selection, plan approval gate, execution progress/cancellation/error retry, result review, and Word export action.

## RED / GREEN evidence

- The focused workflow test was introduced before the UI implementation; the prior implementer recorded RED because `App` did not exist.
- GREEN: `npm run test --workspace apps/desktop -- src/App.test.tsx` passed with 6/6 workflow tests.
- Full desktop GREEN: `npm run test --workspace apps/desktop` passed with 17/17 tests across 3 files.

## Validation

- `npm run typecheck --workspace apps/desktop` — passed.
- `npm run build --workspace apps/desktop` — passed; Vite production bundle generated.
- `git diff --check` — passed.
- The workflow tests cover semantic navigation, approval-before-run, progress/cancellation, non-colour error indication and retry, Turkish switching, explicit Word export, skip link, and labelled native controls.

## Bounded visual / accessibility sanity check

The CSS and DOM were manually reviewed for the Clinical Calm token system (warm paper, clinical-green rail, terracotta actions, serif headings), visible `:focus-visible` treatment, landmark navigation, a skip link, labels, status/alert roles, native progress, and non-colour warning/error marks. A Vite server started successfully, but its loopback port was not reachable from the separate validation process in this sandbox, so no browser screenshot was captured in this task. Production Vite build and jsdom workflow/a11y assertions passed.

## Concerns / intentional boundary

- `createAnalysisApi` deliberately throws for plan/run/cancel/export until Task 11 wires the authenticated local service. It exposes no renderer Node or direct network access.
- The data-intake action uses the existing Electron bridge and shows only the selected file name; parsing/variable inspection remains Task 11 service integration.

## Fix round 1 — independent review findings

RED was established by five new workflow tests, reproducing plan-retry misrouting, missing per-result warning treatment and inspector visibility, incomplete Turkish static copy, unavailable result/report gates and export retry, and an unhandled file-picker rejection.

- Result warnings now receive a visible icon, localized review context, and accessible `note` landmark; plan and result warnings are deduplicated into the scientific inspector.
- English/Turkish parity now includes operation-specific failure banners, run state, report preview, inspector labels/status values, and result interval connector.
- Failure state records `plan`, `analysis`, or `export`, so retry dispatches only the operation that failed. Export failures have a localized retry path.
- Results review and Word report rail entries are disabled until a non-empty validated result collection exists; export is independently guarded as well.
- File-picker exceptions are handled without showing implementation errors or paths.

GREEN: `npm run test --workspace apps/desktop -- src/App.test.tsx` passed 11/11; full desktop suite passed 22/22; typecheck, production build, and `git diff --check` passed.
