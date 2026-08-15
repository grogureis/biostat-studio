# BioStat Studio Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Apple Silicon macOS desktop application that imports Excel data, captures a study brief, proposes and approves a deterministic analysis plan, runs a safe core analysis, previews results, and exports a bilingual Word Results section.

**Architecture:** Electron + React + TypeScript provide the Clinical Calm desktop interface and start a bundled local Python service. FastAPI exposes a loopback-only, token-authenticated API; focused Python modules own data intake, planning, statistical execution, figures, and DOCX reporting. A shared OpenAPI-derived TypeScript contract and versioned project manifest keep the two runtimes synchronized.

**Tech Stack:** Electron, React, TypeScript, Vite, Vitest, Playwright, Python 3.13, FastAPI, Pydantic, pandas, openpyxl, SciPy, statsmodels, matplotlib, python-docx, pytest, PyInstaller, electron-builder.

**Spec:** `docs/superpowers/specs/2026-08-15-biostat-desktop-design.md`

## Global Constraints

- Target Apple Silicon macOS only, including M5; Intel builds are out of scope.
- The application must run locally and offline with no telemetry or external data transfer.
- English is the default UI/report language; Turkish must produce numerically identical results.
- Excel is the primary data format; CSV and SPSS are secondary adapters.
- The original dataset is read-only and must never be overwritten.
- Standard mode requires explicit analysis-plan approval before execution.
- Statistical failures and convergence warnings must never be hidden or narrated as valid findings.
- Every analysis records data fingerprint, plan version, exclusions, transformations, random seed, and library versions.
- Only methods with passing reference fixtures may be exposed in the interface.

## Planned File Structure

```text
.
├── package.json                         # workspace commands and locked JS dependencies
├── electron-builder.yml                # Apple Silicon app and DMG packaging
├── apps/desktop/
│   ├── electron/main.ts                 # Electron lifecycle and sidecar ownership
│   ├── electron/preload.ts              # narrow typed renderer bridge
│   ├── electron/sidecar.ts              # Python service process and readiness
│   ├── src/App.tsx                      # six-stage application composition
│   ├── src/api/client.ts                # authenticated service client
│   ├── src/api/types.ts                 # API DTOs mirrored from Pydantic
│   ├── src/features/project/store.ts    # project state and persistence actions
│   ├── src/features/study/StudyBrief.tsx
│   ├── src/features/data/DataIntake.tsx
│   ├── src/features/plan/PlanReview.tsx
│   ├── src/features/results/ResultsReview.tsx
│   ├── src/features/report/ReportExport.tsx
│   └── src/styles/clinical-calm.css
├── services/analysis/
│   ├── pyproject.toml
│   ├── biostat_service/app.py           # authenticated FastAPI assembly
│   ├── biostat_service/contracts.py     # Pydantic request/result contracts
│   ├── biostat_service/security.py      # token and loopback checks
│   ├── biostat_service/data_intake.py   # immutable Excel load and profile
│   ├── biostat_service/study_model.py   # structured study validation
│   ├── biostat_service/planner.py       # deterministic decision rules
│   ├── biostat_service/analyses.py      # core tested methods
│   ├── biostat_service/visuals.py       # high-resolution figures
│   ├── biostat_service/reporting.py     # bilingual DOCX assembly
│   └── biostat_service/projects.py      # atomic manifest and audit trail
├── tests/fixtures/core-study.xlsx       # deterministic two-group fixture
├── tests/reference/core-study.json      # expected estimates and decisions
└── scripts/package-macos.sh             # sidecar then Electron packaging
```

---

### Task 1: Reproducible Workspace and Shared Contracts

**Files:**
- Create: `.gitignore`
- Create: `package.json`
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/tsconfig.json`
- Create: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/src/api/types.ts`
- Create: `services/analysis/pyproject.toml`
- Create: `services/analysis/biostat_service/contracts.py`
- Test: `services/analysis/tests/test_contracts.py`

**Interfaces:**
- Consumes: approved design specification.
- Produces: `StudyBrief`, `VariableRole`, `PlanItem`, `AnalysisPlan`, and `AnalysisResult` contracts in Pydantic and TypeScript.

- [ ] **Step 0: Create manifests and install repository-local dependencies**

Use npm workspaces for the desktop and an isolated Python virtual environment for the service. The Python manifest declares FastAPI, Pydantic, pandas, openpyxl, SciPy, statsmodels, matplotlib, python-docx, uvicorn, pytest, httpx, and PyInstaller. The desktop manifest declares Electron, React, Vite, TypeScript, Vitest, Testing Library, Playwright, and electron-builder.

Run: `npm install`  
Expected: `package-lock.json` is created.  
Run: `python3 -m venv services/analysis/.venv`  
Run: `services/analysis/.venv/bin/python -m pip install -e 'services/analysis[dev]'`  
Expected: editable `biostat-service` installation succeeds without modifying the system Python.

- [ ] **Step 1: Create the failing contract test**

```python
from pydantic import ValidationError
from biostat_service.contracts import StudyBrief

def test_study_brief_requires_one_outcome():
    try:
        StudyBrief(
            title="30-day outcome",
            question="Does treatment reduce 30-day events?",
            hypothesis="Treatment is associated with fewer events.",
            design="cohort",
            outcome_variables=[],
            exposure_variables=["treatment"],
            language="en",
        )
    except ValidationError as exc:
        assert "outcome_variables" in str(exc)
    else:
        raise AssertionError("empty outcomes must be rejected")
```

- [ ] **Step 2: Run the test and verify the contract is absent**

Run: `cd services/analysis && python3 -m pytest tests/test_contracts.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'biostat_service'`.

- [ ] **Step 3: Define matching Pydantic and TypeScript contracts**

```python
class StudyBrief(BaseModel):
    title: str = Field(min_length=1)
    question: str = Field(min_length=5)
    hypothesis: str = Field(min_length=3)
    design: Literal["cross_sectional", "cohort", "case_control", "trial", "repeated"]
    outcome_variables: list[str] = Field(min_length=1)
    exposure_variables: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    language: Literal["en", "tr"] = "en"
```

Mirror field names exactly in `apps/desktop/src/api/types.ts`; configure the root scripts `test`, `test:python`, `test:desktop`, `dev`, and `package:mac`. Ignore `.venv`, `node_modules`, `dist`, `release`, `.superpowers`, generated reports, and local project data.

- [ ] **Step 4: Run contract tests and type checking**

Run: `cd services/analysis && python3 -m pytest tests/test_contracts.py -v`  
Expected: PASS.  
Run: `npm run typecheck --workspace apps/desktop`  
Expected: exit 0.

- [ ] **Step 5: Commit the workspace boundary**

```bash
git add .gitignore package.json apps/desktop services/analysis
git commit -m "build: scaffold desktop and analysis workspaces"
```

### Task 2: Authenticated Loopback Analysis Service

**Files:**
- Create: `services/analysis/biostat_service/security.py`
- Create: `services/analysis/biostat_service/app.py`
- Test: `services/analysis/tests/test_service_security.py`

**Interfaces:**
- Consumes: environment variable `BIOSTAT_SESSION_TOKEN`.
- Produces: `create_app() -> FastAPI`, `GET /health`, and authenticated `/v1/*` routing.

- [ ] **Step 1: Write security tests**

```python
def test_health_is_available_on_loopback(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok", "service": "biostat-analysis", "api": 1}

def test_v1_rejects_missing_token(client):
    response = client.get("/v1/session")
    assert response.status_code == 401

def test_v1_accepts_session_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd services/analysis && BIOSTAT_SESSION_TOKEN=test-token python3 -m pytest tests/test_service_security.py -v`  
Expected: FAIL because `create_app` is missing.

- [ ] **Step 3: Implement loopback and bearer-token guards**

```python
def require_session(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="loopback_only")
    expected = os.environ["BIOSTAT_SESSION_TOKEN"]
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_session")
```

Bind the command-line server to `127.0.0.1`, accept port `0` through the launcher, and emit one JSON readiness line containing only the selected port and API version.

- [ ] **Step 4: Run security tests**

Run: `cd services/analysis && BIOSTAT_SESSION_TOKEN=test-token python3 -m pytest tests/test_service_security.py -v`  
Expected: 3 PASS.

- [ ] **Step 5: Commit the local service**

```bash
git add services/analysis/biostat_service services/analysis/tests/test_service_security.py
git commit -m "feat: add authenticated loopback analysis service"
```

### Task 3: Electron Lifecycle and Python Sidecar Ownership

**Files:**
- Create: `apps/desktop/electron/sidecar.ts`
- Create: `apps/desktop/electron/main.ts`
- Create: `apps/desktop/electron/preload.ts`
- Create: `apps/desktop/src/global.d.ts`
- Test: `apps/desktop/electron/sidecar.test.ts`

**Interfaces:**
- Consumes: packaged sidecar executable or development command, readiness JSON from stdout.
- Produces: `startSidecar(): Promise<SidecarSession>`, `stopSidecar(): Promise<void>`, and `window.biostat` bridge methods.

- [ ] **Step 1: Write a failing readiness parser test**

```ts
import { describe, expect, it } from 'vitest';
import { parseReadiness } from './sidecar';

describe('parseReadiness', () => {
  it('accepts the versioned local service message', () => {
    expect(parseReadiness('{"port":43117,"api":1}')).toEqual({ port: 43117, api: 1 });
  });
  it('rejects a non-loopback or malformed message', () => {
    expect(() => parseReadiness('{"port":"bad"}')).toThrow('Invalid sidecar readiness');
  });
});
```

- [ ] **Step 2: Verify the test fails**

Run: `npm run test --workspace apps/desktop -- electron/sidecar.test.ts`  
Expected: FAIL because `parseReadiness` is missing.

- [ ] **Step 3: Implement bounded sidecar startup and cleanup**

Generate a 32-byte random token, pass it only through the child environment, parse a single readiness line, enforce a 15-second startup timeout, capture sanitized stderr, and terminate the child on Electron `before-quit`. Use `contextIsolation: true`, `sandbox: true`, and `nodeIntegration: false`. Expose only file selection, project selection, report destination, and authenticated API base/token retrieval through `contextBridge`.

```ts
export function parseReadiness(line: string): SidecarReadiness {
  const value: unknown = JSON.parse(line);
  if (!value || typeof value !== 'object') throw new Error('Invalid sidecar readiness');
  const { port, api } = value as Record<string, unknown>;
  if (!Number.isInteger(port) || Number(port) < 1 || api !== 1) {
    throw new Error('Invalid sidecar readiness');
  }
  return { port: Number(port), api: 1 };
}

const token = randomBytes(32).toString('hex');
const child = spawn(sidecarPath, ['--port', '0'], {
  env: { ...process.env, BIOSTAT_SESSION_TOKEN: token },
  stdio: ['ignore', 'pipe', 'pipe'],
});
```

- [ ] **Step 4: Run desktop unit tests**

Run: `npm run test --workspace apps/desktop -- electron/sidecar.test.ts`  
Expected: PASS.  
Run: `npm run typecheck --workspace apps/desktop`  
Expected: exit 0.

- [ ] **Step 5: Commit lifecycle integration**

```bash
git add apps/desktop/electron apps/desktop/src/global.d.ts
git commit -m "feat: manage the local analysis sidecar"
```

### Task 4: Immutable Excel Intake and Data Profile

**Files:**
- Create: `services/analysis/biostat_service/data_intake.py`
- Create: `tests/fixtures/core-study.xlsx`
- Test: `services/analysis/tests/test_data_intake.py`

**Interfaces:**
- Consumes: `profile_excel(path: Path, sheet: str | None) -> DataProfile`.
- Produces: SHA-256 source fingerprint, sheet list, row/column counts, inferred variable metadata, missingness, duplicates, and structured warnings.

- [ ] **Step 1: Add a deterministic workbook fixture and failing assertions**

```python
def test_profile_excel_detects_roles_and_quality(core_workbook):
    profile = profile_excel(core_workbook, sheet="Analysis")
    assert profile.rows == 12
    assert profile.columns == 5
    assert profile.variables["event_30d"].kind == "binary"
    assert profile.variables["age_years"].kind == "continuous"
    assert profile.missing_cells == 1
    assert len(profile.source_sha256) == 64
```

- [ ] **Step 2: Verify intake is not implemented**

Run: `cd services/analysis && python3 -m pytest tests/test_data_intake.py -v`  
Expected: FAIL importing `profile_excel`.

- [ ] **Step 3: Implement read-only Excel profiling**

Open with pandas/openpyxl without writing to the source. Normalize only display-safe column labels while retaining originals. Classify binary, categorical, continuous, date, identifier-candidate, and free-text variables using explicit thresholds. Return warnings for empty columns, duplicated identifiers, impossible infinities, mixed types, and suspicious identifier leakage.

```python
def profile_excel(path: Path, sheet: str | None = None) -> DataProfile:
    before = sha256_file(path)
    book = pd.ExcelFile(path, engine="openpyxl")
    selected = sheet or book.sheet_names[0]
    frame = pd.read_excel(book, sheet_name=selected)
    variables = {name: infer_variable(frame[name]) for name in frame.columns}
    after = sha256_file(path)
    if before != after:
        raise RuntimeError("source_file_changed")
    return DataProfile(
        source_sha256=before,
        sheets=book.sheet_names,
        selected_sheet=selected,
        rows=len(frame),
        columns=len(frame.columns),
        missing_cells=int(frame.isna().sum().sum()),
        variables=variables,
        warnings=quality_warnings(frame, variables),
    )
```

- [ ] **Step 4: Verify profile and source immutability**

Run: `cd services/analysis && python3 -m pytest tests/test_data_intake.py -v`  
Expected: PASS, including a before/after SHA-256 equality assertion for the workbook.

- [ ] **Step 5: Commit data intake**

```bash
git add services/analysis/biostat_service/data_intake.py services/analysis/tests/test_data_intake.py tests/fixtures/core-study.xlsx
git commit -m "feat: add immutable Excel profiling"
```

### Task 5: Versioned Local Project and Audit Trail

**Files:**
- Create: `services/analysis/biostat_service/projects.py`
- Test: `services/analysis/tests/test_projects.py`

**Interfaces:**
- Consumes: `create_project(root, brief, profile)` and `append_audit_event(project, event)`.
- Produces: versioned `project.json`, `audit.jsonl`, artifact directories, and atomic updates.

- [ ] **Step 1: Write recovery and immutability tests**

```python
def test_project_manifest_is_atomic_and_audited(tmp_path, brief, profile):
    project = create_project(tmp_path / "cardio.biostat", brief, profile)
    append_audit_event(project, {"type": "data_structure_approved", "actor": "user"})
    manifest = json.loads((project.root / "project.json").read_text())
    events = [json.loads(line) for line in (project.root / "audit.jsonl").read_text().splitlines()]
    assert manifest["schema_version"] == 1
    assert manifest["source_sha256"] == profile.source_sha256
    assert events[-1]["type"] == "data_structure_approved"
```

- [ ] **Step 2: Verify project functions are missing**

Run: `cd services/analysis && python3 -m pytest tests/test_projects.py -v`  
Expected: FAIL importing `create_project`.

- [ ] **Step 3: Implement atomic project writes**

Write a sibling temporary file, `fsync`, and replace the manifest atomically. Store only source path, fingerprint, schema, decisions, and generated artifacts; do not copy or mutate the source unless the user explicitly requests a portable export bundle.

```python
def atomic_json_write(destination: Path, value: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, destination)
```

- [ ] **Step 4: Run persistence tests**

Run: `cd services/analysis && python3 -m pytest tests/test_projects.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit persistence**

```bash
git add services/analysis/biostat_service/projects.py services/analysis/tests/test_projects.py
git commit -m "feat: persist versioned local research projects"
```

### Task 6: Deterministic Core Analysis Planner

**Files:**
- Create: `services/analysis/biostat_service/study_model.py`
- Create: `services/analysis/biostat_service/planner.py`
- Create: `tests/reference/core-study.json`
- Test: `services/analysis/tests/test_planner.py`

**Interfaces:**
- Consumes: `build_plan(brief: StudyBrief, profile: DataProfile, roles: dict[str, VariableRole]) -> AnalysisPlan`.
- Produces: versioned plan items with rationale, assumptions, alternatives, estimands, outputs, blocking errors, and warnings.

- [ ] **Step 1: Write failing decision-table tests**

```python
@pytest.mark.parametrize(
    ("outcome_kind", "groups", "paired", "expected"),
    [
        ("continuous", 2, False, "welch_t_test"),
        ("continuous", 2, True, "paired_t_test"),
        ("continuous", 3, False, "welch_anova"),
        ("binary", 2, False, "chi_square_or_fisher"),
    ],
)
def test_primary_group_comparison_rule(outcome_kind, groups, paired, expected):
    assert choose_group_method(outcome_kind, groups, paired).method == expected
```

Add a test that unknown design or an unconfirmed outcome produces a blocking error rather than a guessed test.

- [ ] **Step 2: Verify planner tests fail**

Run: `cd services/analysis && python3 -m pytest tests/test_planner.py -v`  
Expected: FAIL importing `choose_group_method`.

- [ ] **Step 3: Implement explicit rules and plan serialization**

Use a small decision table for the verified vertical slice: descriptive summary, two/multi-group continuous comparison, paired comparison, categorical association, correlation, and single-outcome linear/logistic regression. Plan nonparametric alternatives when distribution/robustness checks indicate them, but do not select solely from a normality p-value. Include effect sizes and 95% confidence intervals in every output contract.

```python
def choose_group_method(outcome_kind: str, groups: int, paired: bool) -> PlanChoice:
    rules = {
        ("continuous", 2, False): ("welch_t_test", "mann_whitney_u"),
        ("continuous", 2, True): ("paired_t_test", "wilcoxon_signed_rank"),
        ("continuous", 3, False): ("welch_anova", "kruskal_wallis"),
        ("binary", 2, False): ("chi_square_or_fisher", None),
    }
    key = (outcome_kind, 3 if groups > 2 else groups, paired)
    if key not in rules:
        raise BlockingPlanError("unsupported_or_unconfirmed_design")
    method, alternative = rules[key]
    return PlanChoice(method=method, robust_alternative=alternative)
```

- [ ] **Step 4: Run planner tests and snapshot the reference plan**

Run: `cd services/analysis && python3 -m pytest tests/test_planner.py -v`  
Expected: PASS and `tests/reference/core-study.json` matches the approved plan structure.

- [ ] **Step 5: Commit the planner**

```bash
git add services/analysis/biostat_service/study_model.py services/analysis/biostat_service/planner.py services/analysis/tests/test_planner.py tests/reference/core-study.json
git commit -m "feat: plan core analyses deterministically"
```

### Task 7: Core Statistical Execution and Scientific Result Objects

**Files:**
- Create: `services/analysis/biostat_service/analyses.py`
- Test: `services/analysis/tests/test_analyses_reference.py`

**Interfaces:**
- Consumes: `run_plan(frame: pd.DataFrame, plan: AnalysisPlan) -> AnalysisBundle`.
- Produces: structured estimates, confidence intervals, exact p-values, diagnostics, exclusions, warnings, and reproducibility metadata.

- [ ] **Step 1: Add known-result tests**

```python
def test_welch_result_matches_reference(core_frame, approved_plan):
    bundle = run_plan(core_frame, approved_plan)
    result = bundle.results["primary_outcome"]
    assert result.method == "welch_t_test"
    assert result.n == 11
    assert result.estimate == pytest.approx(-4.1667, abs=1e-4)
    assert result.confidence_interval.level == 0.95
    assert 0.0 <= result.p_value <= 1.0
    assert result.effect_size.name == "hedges_g"
```

Add invariance tests for row reordering and English/Turkish language selection.

- [ ] **Step 2: Verify execution tests fail**

Run: `cd services/analysis && python3 -m pytest tests/test_analyses_reference.py -v`  
Expected: FAIL importing `run_plan`.

- [ ] **Step 3: Implement the verified core registry**

Implement a method registry keyed by the planner's method identifiers. Use SciPy/statsmodels for estimates and diagnostics; calculate Hedges' g and confidence intervals with documented formulas. Reject non-finite inputs, preserve missing-data counts, and convert package warnings into structured warning objects. Stamp Python and library versions into the bundle.

```python
METHODS: dict[str, Callable[[pd.DataFrame, PlanItem], AnalysisResult]] = {
    "welch_t_test": run_welch_t,
    "paired_t_test": run_paired_t,
    "welch_anova": run_welch_anova,
    "chi_square_or_fisher": run_categorical_association,
    "pearson_or_spearman": run_correlation,
    "linear_regression": run_linear_regression,
    "logistic_regression": run_logistic_regression,
}

def run_plan(frame: pd.DataFrame, plan: AnalysisPlan) -> AnalysisBundle:
    results = {item.id: METHODS[item.method](frame, item) for item in plan.items}
    return AnalysisBundle(results=results, reproducibility=runtime_versions())
```

- [ ] **Step 4: Run all scientific tests**

Run: `cd services/analysis && python3 -m pytest tests/test_planner.py tests/test_analyses_reference.py -v`  
Expected: PASS with no uncaptured warnings.

- [ ] **Step 5: Commit execution**

```bash
git add services/analysis/biostat_service/analyses.py services/analysis/tests/test_analyses_reference.py
git commit -m "feat: execute verified core statistical analyses"
```

### Task 8: Publication-Quality Figure Generation

**Files:**
- Create: `services/analysis/biostat_service/visuals.py`
- Test: `services/analysis/tests/test_visuals.py`

**Interfaces:**
- Consumes: `build_figures(frame, plan, bundle, output_dir, language) -> list[FigureArtifact]`.
- Produces: 300-DPI PNG, SVG where supported, localized caption, alt text, and dimensions.

- [ ] **Step 1: Write artifact and accessibility tests**

```python
def test_group_figure_has_png_svg_caption_and_alt_text(tmp_path, core_frame, approved_plan, bundle):
    figures = build_figures(core_frame, approved_plan, bundle, tmp_path, "en")
    primary = figures[0]
    assert primary.png_path.exists()
    assert primary.svg_path.exists()
    assert primary.dpi == 300
    assert "group" in primary.alt_text.lower()
    assert primary.caption.startswith("Figure 1.")
```

- [ ] **Step 2: Verify visual tests fail**

Run: `cd services/analysis && MPLBACKEND=Agg python3 -m pytest tests/test_visuals.py -v`  
Expected: FAIL importing `build_figures`.

- [ ] **Step 3: Implement a Clinical Calm scientific theme**

Use a color-vision-safe deep-green/terracotta palette, explicit figure sizing for journal columns, visible data distributions rather than bar-only summaries, English/Turkish labels, and deterministic ordering. Close every matplotlib figure after saving.

```python
def save_figure(fig: Figure, stem: Path) -> tuple[Path, Path]:
    png = stem.with_suffix(".png")
    svg = stem.with_suffix(".svg")
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor="#fffdf8")
    fig.savefig(svg, bbox_inches="tight", facecolor="#fffdf8")
    plt.close(fig)
    return png, svg
```

- [ ] **Step 4: Run visual tests and inspect the fixture image**

Run: `cd services/analysis && MPLBACKEND=Agg python3 -m pytest tests/test_visuals.py -v`  
Expected: PASS. Open the generated PNG at 100% and verify unclipped labels, legible type, and sensible contrast.

- [ ] **Step 5: Commit figures**

```bash
git add services/analysis/biostat_service/visuals.py services/analysis/tests/test_visuals.py
git commit -m "feat: generate accessible publication figures"
```

### Task 9: Bilingual Word Results Report

**Files:**
- Create: `services/analysis/biostat_service/reporting.py`
- Test: `services/analysis/tests/test_reporting.py`
- Test: `services/analysis/tests/test_reporting_parity.py`

**Interfaces:**
- Consumes: `build_results_docx(project, brief, plan, bundle, figures, language, destination) -> Path`.
- Produces: editable `.docx` with Results prose, numbered Word-native tables, embedded figures, captions, notes, alt text, and reproducibility appendix.

- [ ] **Step 1: Write structural and bilingual parity tests**

```python
def test_results_docx_contains_required_sections(report_en):
    doc = Document(report_en)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Results" in text
    assert "95% CI" in text
    assert "Table 1" in text
    assert len(doc.tables) >= 1

def test_turkish_and_english_reports_share_numerical_tokens(report_en, report_tr):
    assert extract_numeric_tokens(report_en) == extract_numeric_tokens(report_tr)
```

- [ ] **Step 2: Verify reporting tests fail**

Run: `cd services/analysis && python3 -m pytest tests/test_reporting.py tests/test_reporting_parity.py -v`  
Expected: FAIL importing `build_results_docx`.

- [ ] **Step 3: Implement deterministic narrative and document styling**

Generate prose from structured result templates rather than free-form AI. Report estimates, 95% confidence intervals, exact p-values, denominators, missingness, and material warnings. Use Word-native tables with repeating headers and generous cell padding; keep figure/caption pairs together; add meaningful image alt text; avoid causal claims for observational designs.

```python
RESULT_LABELS = {
    "en": {"heading": "Results", "table": "Table", "figure": "Figure"},
    "tr": {"heading": "Bulgular", "table": "Tablo", "figure": "Şekil"},
}

def format_p_value(value: float) -> str:
    return "p < 0.001" if value < 0.001 else f"p = {value:.3f}"

def build_results_docx(project, brief, plan, bundle, figures, language, destination):
    labels = RESULT_LABELS[language]
    document = Document()
    document.add_heading(labels["heading"], level=1)
    add_results_narrative(document, brief, plan, bundle, language)
    add_result_tables(document, bundle, labels)
    add_figures(document, figures)
    add_reproducibility_appendix(document, bundle)
    document.save(destination)
    return Path(destination)
```

- [ ] **Step 4: Render and visually inspect both reports**

Run: `cd services/analysis && python3 -m pytest tests/test_reporting.py tests/test_reporting_parity.py -v`  
Expected: PASS.  
Run the Documents skill renderer against both fixture DOCX files and inspect every page PNG at 100%. Expected: no clipping, overlap, orphan captions, blank overflow pages, or numeric differences.

- [ ] **Step 5: Commit reporting**

```bash
git add services/analysis/biostat_service/reporting.py services/analysis/tests/test_reporting.py services/analysis/tests/test_reporting_parity.py
git commit -m "feat: export bilingual Word results reports"
```

### Task 10: Clinical Calm Six-Stage Desktop Workflow

**Files:**
- Create: `apps/desktop/src/main.tsx`
- Create: `apps/desktop/src/App.tsx`
- Create: `apps/desktop/src/api/client.ts`
- Create: `apps/desktop/src/features/project/store.ts`
- Create: `apps/desktop/src/features/study/StudyBrief.tsx`
- Create: `apps/desktop/src/features/data/DataIntake.tsx`
- Create: `apps/desktop/src/features/plan/PlanReview.tsx`
- Create: `apps/desktop/src/features/results/ResultsReview.tsx`
- Create: `apps/desktop/src/features/report/ReportExport.tsx`
- Create: `apps/desktop/src/styles/clinical-calm.css`
- Test: `apps/desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: `window.biostat`, authenticated API client, and shared DTOs.
- Produces: accessible six-stage workflow with explicit approval, progress, warnings, retry, cancellation, language, and export actions.

- [ ] **Step 1: Write the failing workflow test**

```tsx
it('requires plan approval before running analysis', async () => {
  render(<App api={fakeApiWithPlan()} />);
  await userEvent.click(screen.getByRole('button', { name: /analysis plan/i }));
  expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /approve this plan/i }));
  expect(screen.getByRole('button', { name: /run analysis/i })).toBeEnabled();
});
```

- [ ] **Step 2: Verify workflow test fails**

Run: `npm run test --workspace apps/desktop -- src/App.test.tsx`  
Expected: FAIL because `App` is missing.

- [ ] **Step 3: Implement the approved interface flow**

Use the selected Clinical Calm tokens: warm white surfaces, deep clinical green navigation, restrained terracotta primary actions, serif display typography, and visible offline status. Keep the active task central and scientific explanations in the right inspector. Implement keyboard-visible focus, semantic labels, non-color warning icons, loading/progress states, cancellation, and English/Turkish UI copy.

```tsx
export function App({ api }: { api: AnalysisApi }) {
  const project = useProjectStore();
  return (
    <AppShell language={project.language} offline>
      <WorkflowRail activeStep={project.activeStep} />
      <main id="workspace">
        {project.activeStep === 'study' && <StudyBrief api={api} />}
        {project.activeStep === 'data' && <DataIntake api={api} />}
        {project.activeStep === 'plan' && <PlanReview api={api} />}
        {project.activeStep === 'results' && <ResultsReview api={api} />}
        {project.activeStep === 'report' && <ReportExport api={api} />}
      </main>
      <ScientificInspector warnings={project.warnings} />
    </AppShell>
  );
}
```

- [ ] **Step 4: Run UI tests and accessibility assertions**

Run: `npm run test --workspace apps/desktop`  
Expected: PASS.  
Run: `npm run typecheck --workspace apps/desktop`  
Expected: exit 0.

- [ ] **Step 5: Commit the desktop workflow**

```bash
git add apps/desktop/src
git commit -m "feat: add the Clinical Calm analysis workflow"
```

### Task 11: API Wiring, Jobs, Cancellation, and End-to-End Fixture

**Files:**
- Modify: `services/analysis/biostat_service/app.py`
- Create: `services/analysis/biostat_service/jobs.py`
- Modify: `apps/desktop/src/api/client.ts`
- Create: `apps/desktop/e2e/core-workflow.spec.ts`
- Test: `services/analysis/tests/test_jobs.py`

**Interfaces:**
- Consumes: intake, projects, planner, analyses, visuals, reporting.
- Produces: `/v1/projects`, `/v1/data/profile`, `/v1/plans`, `/v1/jobs`, `/v1/jobs/{id}`, `/v1/jobs/{id}/cancel`, and `/v1/reports` endpoints plus the complete UI flow.

- [ ] **Step 1: Write job-state and end-to-end tests**

```python
def test_cancelled_job_never_becomes_completed(job_manager):
    job = job_manager.submit(slow_test_job)
    job_manager.cancel(job.id)
    final = job_manager.wait(job.id)
    assert final.status == "cancelled"
    assert final.result is None
```

```ts
test('imports, approves, analyzes, and exports', async ({ page }) => {
  await page.getByRole('button', { name: 'Import Excel' }).click();
  await expect(page.getByText('12 observations')).toBeVisible();
  await page.getByRole('button', { name: 'Approve data structure' }).click();
  await page.getByLabel('Approve this plan').check();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible();
  await page.getByRole('button', { name: 'Export Word report' }).click();
});
```

- [ ] **Step 2: Verify tests fail on missing routes**

Run: `cd services/analysis && python3 -m pytest tests/test_jobs.py -v`  
Expected: FAIL importing `JobManager`.  
Run: `npm run test:e2e --workspace apps/desktop`  
Expected: FAIL before the workflow completes.

- [ ] **Step 3: Implement versioned endpoints and cancellable background jobs**

Keep job state in the project, use bounded worker concurrency, publish progress stages, and make cancellation cooperative between analysis steps. Return machine-readable error codes plus safe localized messages; never include raw patient values in logs.

```python
@router.post("/jobs", response_model=JobState)
def create_job(request: RunAnalysisRequest, session: Session = Depends(require_session)):
    return job_manager.submit(
        project_id=request.project_id,
        plan_version=request.approved_plan_version,
        operation=run_approved_analysis,
    )

@router.post("/jobs/{job_id}/cancel", response_model=JobState)
def cancel_job(job_id: UUID, session: Session = Depends(require_session)):
    return job_manager.cancel(job_id)
```

- [ ] **Step 4: Run service, desktop, and end-to-end tests**

Run: `npm test`  
Expected: all Python, Vitest, and Playwright tests PASS.

- [ ] **Step 5: Commit the complete vertical slice**

```bash
git add services/analysis apps/desktop
git commit -m "feat: connect the end-to-end biostatistics workflow"
```

### Task 12: Apple Silicon Packaging and Clean-Launch Verification

**Files:**
- Create: `services/analysis/biostat_service/__main__.py`
- Create: `services/analysis/biostat-service.spec`
- Create: `electron-builder.yml`
- Create: `scripts/package-macos.sh`
- Create: `apps/desktop/build/icon.icns`
- Create: `README.md`
- Test: `scripts/smoke-packaged-app.sh`

**Interfaces:**
- Consumes: passing vertical slice and application icon assets.
- Produces: unsigned Apple Silicon `BioStat Studio.app` and `.dmg` containing the Python sidecar and required scientific libraries.

- [ ] **Step 1: Write a failing packaged-resource smoke test**

```bash
#!/usr/bin/env bash
set -euo pipefail
APP="release/mac-arm64/BioStat Studio.app"
test -d "$APP"
test -x "$APP/Contents/Resources/bin/biostat-service"
"$APP/Contents/Resources/bin/biostat-service" --self-test
```

- [ ] **Step 2: Verify packaging check fails before artifacts exist**

Run: `bash scripts/smoke-packaged-app.sh`  
Expected: FAIL because the `.app` does not exist.

- [ ] **Step 3: Package the sidecar and Electron application**

Build the Python executable with PyInstaller for `arm64`, copy it into Electron resources, build the renderer/main process, and run electron-builder with `mac.target = ["dmg", "dir"]` and `mac.arch = ["arm64"]`. Include a generated Clinical Calm application icon with the required macOS icon sizes. Do not enable signing until a Developer ID is available.

```bash
#!/usr/bin/env bash
set -euo pipefail
python3 -m PyInstaller services/analysis/biostat-service.spec --noconfirm
npm run build --workspace apps/desktop
npx electron-builder --mac dmg dir --arm64
bash scripts/smoke-packaged-app.sh
```

- [ ] **Step 4: Verify the packaged app**

Run: `npm test`  
Expected: all tests PASS.  
Run: `npm run package:mac`  
Expected: `.app` and `.dmg` created under `release/`.  
Run: `bash scripts/smoke-packaged-app.sh`  
Expected: PASS. Launch the `.app`, import the fixture, complete the flow, reopen the saved project, export English and Turkish reports, and confirm no internet connection is required.

- [ ] **Step 5: Commit packaging and release instructions**

```bash
git add electron-builder.yml scripts services/analysis/biostat-service.spec apps/desktop/build/icon.icns README.md
git commit -m "build: package BioStat Studio for Apple Silicon"
```

## Follow-on Validated Plans

After this vertical slice passes clean-machine verification, create and execute separate implementation plans in this order:

1. `additional-input-adapters`: CSV/SPSS data import plus local Word/PDF extraction for study questions and hypotheses.
2. `advanced-statistics`: repeated measures, mixed models, survival, ROC, missing-data workflows, power/sample size, and meta-analysis, each with independent reference fixtures.
3. `machine-learning`: leakage-safe preprocessing, grouped/nested validation, model comparison, calibration, threshold analysis, clustering, and explanation fixtures.
4. `release-hardening`: accessibility audit, large-dataset performance, autosave/crash recovery, signing, notarization, updater decision, and public distribution documentation.

These plans must reuse the contracts and result/report interfaces established here and must not expose a method before its reference suite passes.
