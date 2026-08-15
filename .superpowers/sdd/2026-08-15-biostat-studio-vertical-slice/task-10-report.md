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
