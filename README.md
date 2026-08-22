# BioStat Studio

BioStat Studio is an offline-first Apple Silicon macOS application for a guided biostatistics workflow: Excel intake, study-brief capture, data-structure and analysis-plan approval, local analysis, and bilingual Word results export.

## Clean checkout and local development

The repository uses only local dependencies. From a clean checkout, install the locked Node workspace packages and create the repository-local Python environment:

```bash
npm ci --no-audit --no-fund
bash scripts/bootstrap-analysis-venv.sh
```

The bootstrap script creates or reuses `services/analysis/.venv`, installs the pinned `services/analysis/requirements.lock` dependencies, then installs the local analysis package without system-wide changes. It stores a lock-file hash stamp and skips reinstalling unchanged environments. Start the desktop shell with:

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
