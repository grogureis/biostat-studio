# BioStat Studio

BioStat Studio is an offline-first Apple Silicon macOS application for a guided biostatistics workflow: Excel intake, study-brief capture, data-structure and analysis-plan approval, local analysis, and bilingual Word results export.

## Local development

The repository uses only local dependencies: `npm install` for the Electron workspace and `services/analysis/.venv` for the Python service. Start the desktop shell with:

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

On an Apple Silicon Mac, build an unsigned local package with:

```bash
npm run package:mac
```

The command creates `release/mac-arm64/BioStat Studio.app` and an arm64 DMG in `release/`, then runs the packaged-resource smoke test. The package has no telemetry and starts its authenticated analysis service only on `127.0.0.1` with an ephemeral port.

The first release is intentionally unsigned and not notarized. Gatekeeper warnings for copies shared with other people are expected until a later Developer ID signing and notarization release.
