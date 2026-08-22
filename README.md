# BioStat Studio

BioStat Studio is an offline-first Apple Silicon macOS application for a guided biostatistics workflow: Excel intake, study-brief capture, data-structure and analysis-plan approval, local analysis, and bilingual Word results export.

## Verified vertical-slice scope

The current application accepts `.xlsx` workbooks and executes descriptive summaries, Welch independent-samples and paired t tests, Welch ANOVA, chi-square/Fisher testing, Pearson correlation, and linear and logistic regression. The guided planner records assumptions, provenance, and pre-planned nonparametric alternatives, but Mann–Whitney U, Wilcoxon signed-rank, Kruskal–Wallis, and Spearman correlation are not automatically executed in this release. Explicit data-role and immutable-plan approval are required before execution.

CSV and SAV importers are future adapters. Advanced statistics, machine learning, validated prediction-model development, and causal-inference workflows are also future work; the current release does not claim those capabilities.

## Clean checkout and local development

Install Python 3.12 first (for example, `brew install python@3.12`). From a clean checkout, install the locked Node workspace packages and create the repository-local Python environment:

```bash
npm ci --no-audit --no-fund
bash scripts/bootstrap-analysis-venv.sh
```

The bootstrap script requires Python 3.12, creates or reuses `services/analysis/.venv-py312`, installs the pinned `services/analysis/requirements.lock` dependencies, then installs the local analysis package without changing macOS system Python. Its lock stamp includes both the dependency hash and interpreter version, and it skips reinstalling an unchanged environment. Start the desktop shell with:

```bash
npm run dev
```

Run the service and desktop suites with:

```bash
npm test
npm run typecheck --workspace apps/desktop
npm run build --workspace apps/desktop
```

## Apple Silicon package

On an Apple Silicon Mac, build a local package without Developer ID distribution signing with:

```bash
npm run package:mac
```

The command creates `release/mac-arm64/BioStat Studio.app` and an arm64 DMG in `release/`, then runs the packaged-resource smoke test. The package has no telemetry and starts its authenticated analysis service only on `127.0.0.1` with an ephemeral port.

The first release has no Developer ID or distribution signing and is not notarized. Electron Builder applies the required ad-hoc arm64 signatures while packaging; Gatekeeper warnings for copies shared with other people are expected until a later Developer ID signing and notarization release.
