# BioStat Studio documentation visuals

Remotion sources for the English and Turkish README illustrations. The palette follows the desktop application's `clinical-calm.css`: paper, forest green and terracotta. These are explanatory illustrations, not UI screenshots or clinical results.

This is an independent Node project outside the root `apps/*` workspace. Its dependencies and lockfile do not affect the desktop package or analysis service.

## Preview and edit

Requires Node.js 22 or newer and npm. From the repository root:

```bash
cd docs/remotion
npm ci --no-audit --no-fund
npm run studio
```

Open the exact localhost URL printed by Remotion. The `--no-open` option prevents automatic opening of the system browser.

| Composition | Purpose |
| --- | --- |
| `HeroEN` / `HeroTR` | Product overview, local analysis and explicit researcher approval |
| `WorkflowEN` / `WorkflowTR` | Six-stage analysis path and independent power/sample-size tool |
| `ReportEN` / `ReportTR` | Editable Word output, bilingual parity and reproducibility |
| `WorkflowMotionEN` / `WorkflowMotionTR` | 18-second workflow animation at 30 fps |

Each language/composition has its own registration in `src/Root.tsx`. Shared components keep both languages visually consistent. Animation is driven by Remotion frames, not CSS timers. The stage cards are generated from a shared bilingual template.

## Regenerate the README images

```bash
npm run typecheck
npm run assets
```

The asset command exports six 1600 × 900 PNG files to `docs/assets/`. Remotion downloads Chrome Headless Shell on first use. Commit regenerated images with their source changes so GitHub can display them without a build step. Static images stay fully legible when viewed without motion.

The animation is available in Studio; no video export is required to read the README. Optional export, when needed:

```bash
npx remotion render src/index.ts WorkflowMotionTR /tmp/biostat-workflow.tr.mp4
```

## Content boundaries

- Study metadata and machine suggestions remain subject to researcher review.
- Data/variable confirmation and analysis-plan approval are separate gates.
- Power/sample size is independent of imported data.
- Results and reports derive from completed jobs; changes invalidate downstream approvals.
- The Word illustration deliberately contains no study estimates or fabricated results.
- Pre-release status and operator acceptance requirements remain visible in both READMEs.
- Do not represent roadmap analyses as implemented features.
