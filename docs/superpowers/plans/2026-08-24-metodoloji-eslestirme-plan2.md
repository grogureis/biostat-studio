# Metodoloji Eşleştirme ve Çelişki Çözümü — Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yüklenen metodoloji belgesi çalışmanın kalıcı parçası haline gelir; program belgedeki kavramları Excel sütunlarıyla eşleştirir, veriyle belge çeliştiğinde çelişkinin **analiz üzerindeki bedelini** `planner`'a gerçekten hesaplatıp kullanıcıya gösterir ve kararı kullanıcıya bıraktırır.

**Architecture:** Belgeden çıkarılan **ham metin** proje klasöründe yaşar (`source/methodology.txt` + manifest bloğu); renderer yalnızca proje doğana kadar köprüdür. Eşleştirme ve çelişki tespiti deterministik koddur; LLM bu planda **yoktur** (Plan 3). Çelişkinin bedelini `planner.build_plan` iki farklı girdiyle çağrılarak hesaplar — tahmin edilmez. `planner.py`, `analyses.py`, `power.py`, `reporting.py` bu planda da **hiç değişmez**.

**Tech Stack:** Python 3.12 · FastAPI · pydantic v2 · pandas · Electron 37 · React 19 · TypeScript · vitest · pytest

**Spec:** `docs/superpowers/specs/2026-08-24-metodoloji-cikarimi-design.md` (§5, §6)
**Devralınan kararlar:** `docs/STATE.md` madde **0d** (belgenin evi), **0e** (hazır altyapı), **0b** (Plan 1 borçları)

---

## Global Constraints

- Python `>=3.12,<3.13`.
- **Python test komutu:** `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
  `npm run test:python` bu worktree'de **BOZUK** (venv editable kablolaması; kök neden `doğrulanmadı`). Yukarıdaki biçimi kullanın. `[ÖLÇÜM 2026-08-24: 280 passed]`
- **Desktop test:** `npm run test:desktop` · **Typecheck:** `npm run typecheck --workspace apps/desktop` `[ÖLÇÜM: ikisi de çalışıyor]`
- **Yeni bağımlılık yok.** Bulanık eşleştirme `difflib` (stdlib) ile yapılır; `rapidfuzz`/`thefuzz` eklenmez.
- **Değişmez dosyalar:** `planner.py`, `analyses.py`, `power.py`, `reporting.py`. Bu plandaki hiçbir task bunları düzenlemez.
- **Plan determinizmi:** aynı girdi → aynı metot → aynı digest. Eşleştirme skorları `float` sıralamasına bağlıysa **stabil tie-break** (isim alfabetik) zorunlu.
- **Fail-closed:** çözülmemiş çelişki varken `data_structure_approved` **true olamaz**.
- Renderer dosya yolu görmez; capability token deseni (`main.ts:74-83`, `api-proxy.ts:43-72`) korunur.
- Hiçbir hata mesajı, uyarı veya log **hücre değeri ya da dosya yolu içermez**.
- `ColumnSummary`'de **hücre değeri taşınmaz** (spec §5) — gizlilik bir politika değil, tip imzası.
- Bilingual: kullanıcıya görünen her string TR ve EN.
- `MAX_DOCUMENT_CHARS = 200_000` (mevcut). Projede **ham metin** saklanır, kırpılmış seçim değil (STATE.md 0d).

---

## File Structure

| Dosya | Sorumluluk | Durum |
|---|---|---|
| `services/analysis/biostat_service/projects.py` | Belgeyi projeye yazma/okuma, manifest bloğu | Modify |
| `services/analysis/biostat_service/app.py` | Endpoint yüzeyi, çelişki hesabı, context | Modify |
| `services/analysis/biostat_service/extractors/contracts.py` | `ColumnSummary`, `RoleProposal`, `MethodologyExtractor` | Modify |
| `services/analysis/biostat_service/extractors/matching.py` | Normalizasyon + bulanık eşleştirme çekirdeği | **Create** |
| `services/analysis/biostat_service/extractors/rule.py` | `match_variables` + doküman kaynaklı `kind` iddiası | Modify |
| `services/analysis/biostat_service/variable_reconciliation.py` | Çelişki tespiti + `build_plan` ile bedel hesabı | **Create** |
| `apps/desktop/electron/api-proxy.ts` | Yeni rota allowlist'i | Modify |
| `apps/desktop/src/api/types.ts`, `client.ts` | Yeni DTO'lar ve çağrılar | Modify |
| `apps/desktop/src/features/project/store.ts`, `App.tsx` | Belge metninin köprülenmesi | Modify |
| `apps/desktop/src/features/study/StudyBrief.tsx` | Yerel `extraction` state'inin yukarı taşınması | Modify |
| `apps/desktop/src/features/data/DataIntake.tsx` | Çelişki bloğu, rozetler, toplu kabul, `confirmed` düzeltmesi | Modify |

**Neden `variable_reconciliation.py` ayrı dosya:** `build_plan`'ı iki kez çağırıp iki planı karşılaştıran mantık ne `app.py`'nin HTTP işi ne de `extractors/`'ın dil işi. Ayrı tutulmazsa `app.py`'nin zaten 950+ satırlık gövdesine karışır ve `planner`'a dokunmama sınırı gözden kaybolur.

---

### Task 1: Belgenin evi — proje kalıcılığı

Belge, çalışmanın kalıcı parçası (STATE.md 0d). Excel'in kopyalanma deseninin (`projects.py:508`) yanına metodoloji metni yazılır.

**Files:**
- Modify: `services/analysis/biostat_service/projects.py`
- Test: `services/analysis/tests/test_projects.py`

**Interfaces:**
- Consumes: `methodology_intake.MethodologyDocument` (mevcut: `source_sha256`, `source_format`, `text`, `char_count`, `truncated`, `warnings`)
- Produces:
  - `attach_methodology(project: LocalProject, document: MethodologyDocument, original_name: str) -> None`
  - `read_methodology(project: LocalProject) -> MethodologyRecord | None`
  - `@dataclass(frozen=True) class MethodologyRecord: text: str; source_sha256: str; source_format: str; original_name: str; char_count: int; truncated: bool`

**Ölçülmüş kolaylık:** `_validate_relative_references` (`projects.py:310`) özyinelemeli olarak her `relative_path` anahtarını doğruluyor, dolayısıyla `methodology.relative_path` **ek kod olmadan** güvenlik kontrolünden geçer. `_read_manifest` bilinmeyen üst-düzey alanları reddetmiyor → `SCHEMA_VERSION` **2'de kalır**, migration yazılmaz, belgesi olmayan eski projeler geçerli kalır.

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_projects.py sonuna
from biostat_service.methodology_intake import MethodologyDocument
from biostat_service.projects import attach_methodology, read_methodology


def _document(text: str = "Yöntem\nRetrospektif kohort çalışması.") -> MethodologyDocument:
    return MethodologyDocument(
        source_sha256="a" * 64,
        source_format="docx",
        text=text,
        char_count=len(text),
        truncated=False,
        warnings=(),
    )


def test_attached_methodology_survives_a_reload(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "data.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "study.biostat", brief, profile_excel(source))

    attach_methodology(project, _document(), "yontem.docx")

    reloaded, manifest = load_project(project.root)
    record = read_methodology(reloaded)
    assert record is not None
    assert record.text == "Yöntem\nRetrospektif kohort çalışması."
    assert record.original_name == "yontem.docx"
    assert record.source_format == "docx"
    assert manifest["methodology"]["relative_path"] == "source/methodology.txt"
    assert manifest["schema_version"] == 2


def test_a_project_without_a_document_reads_as_none(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "data.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "study.biostat", brief, profile_excel(source))

    assert read_methodology(project) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_projects.py -q -k methodology`
Expected: FAIL — `ImportError: cannot import name 'attach_methodology'`

- [ ] **Step 3: Write minimal implementation**

```python
# projects.py — MethodologyDocument import'u fonksiyon içinde tutulur (döngüsel
# import: methodology_intake modül düzeyinde projects'i çekmiyor ama ileride
# çekerse bu sıralama kırılır; data_intake.sha256_file'ın load_project içinde
# geç import edilmesiyle aynı gerekçe, projects.py:424).

METHODOLOGY_RELATIVE = Path("source") / "methodology.txt"


@dataclass(frozen=True)
class MethodologyRecord:
    """One methodology document as the project durably remembers it."""

    text: str
    source_sha256: str
    source_format: str
    original_name: str
    char_count: int
    truncated: bool


def attach_methodology(
    project: LocalProject, document: Any, original_name: str
) -> None:
    """Store the extracted text next to the workbook snapshot, atomically.

    The ORIGINAL .docx/.pdf is deliberately NOT copied (STATE.md 0d): the only
    thing it could yield was text, and the text is already here. Its name and
    sha256 are kept so "which document did this come from" stays answerable.
    """
    destination = _safe_relative_reference(project.root, METHODOLOGY_RELATIVE.as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text_write(destination, document.text)
    manifest = _read_manifest(project)
    manifest["methodology"] = {
        "relative_path": METHODOLOGY_RELATIVE.as_posix(),
        "sha256": document.source_sha256,
        "source_format": document.source_format,
        "original_name": original_name,
        "char_count": document.char_count,
        "truncated": document.truncated,
    }
    _validate_relative_references(project.root, manifest)
    atomic_json_write(project.manifest_path, manifest)


def read_methodology(project: LocalProject) -> MethodologyRecord | None:
    """Read the stored document text, or None when the study has no document."""
    manifest = _read_manifest(project)
    record = manifest.get("methodology")
    if not isinstance(record, Mapping):
        return None
    path = _safe_relative_reference(project.root, record.get("relative_path"))
    if not path.is_file():
        raise ValueError("methodology_document_missing")
    return MethodologyRecord(
        text=path.read_text(encoding="utf-8"),
        source_sha256=str(record.get("sha256", "")),
        source_format=str(record.get("source_format", "")),
        original_name=str(record.get("original_name", "")),
        char_count=int(record.get("char_count", 0)),
        truncated=bool(record.get("truncated", False)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_projects.py -q`
Expected: PASS (mevcut testler dahil)

- [ ] **Step 5: Düzelt — yanlış docstring**

`create_project`'in docstring'i *"without copying its source dataset"* diyor ama `projects.py:511` çalışma kitabını gerçekten kopyalıyor (`test_projects.py:75` doğruluyor). `[ÖLÇÜM 2026-08-24]` Docstring'i gerçeğe uydurun:

```python
def create_project(root: Path, brief: StudyBrief, profile: DataProfile) -> LocalProject:
    """Create or reopen one project folder, snapshotting its source workbook."""
```

- [ ] **Step 6: Commit**

```bash
git add services/analysis/biostat_service/projects.py services/analysis/tests/test_projects.py
git commit -m "feat: give the methodology document a durable home in the project"
```

---

### Task 2: Servis yüzeyi — belge projeye nasıl girer

Belge iki yoldan projeye girebilmeli: proje **doğarken** (renderer köprüsüyle) ve proje **açıkken** (doğrudan).

**Files:**
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `services/analysis/biostat_service/projects.py` (`AUDIT_EVENT_TYPES`)
- Test: `services/analysis/tests/test_methodology_endpoint.py`

**Interfaces:**
- Consumes: `attach_methodology`, `read_methodology`, `MethodologyRecord` (Task 1)
- Produces:
  - `/v1/methodology/extract` yanıtına `text: str` ve `original_name: str` eklenir
  - `ProjectRequest.methodology: MethodologyPayload | None`
  - `POST /v1/projects/{project_id}/methodology` → `{"attached": true}`
  - `ProjectContext.methodology: MethodologyRecord | None`
  - `class MethodologyPayload(BaseModel): text: str; source_sha256: str; source_format: str; original_name: str; char_count: int; truncated: bool`

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_methodology_endpoint.py sonuna
def test_extract_returns_the_full_text_for_the_renderer_to_carry(
    client: TestClient, tmp_path: Path
) -> None:
    path = tmp_path / "m.txt"
    path.write_text("Yöntem\nRetrospektif kohort çalışması.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    body = response.json()
    assert body["text"] == "Yöntem\nRetrospektif kohort çalışması."
    assert body["original_name"] == "m.txt"


def test_document_attached_to_an_open_project_is_readable_again(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client, tmp_path)  # bkz. Step 1b

    response = client.post(
        f"/v1/projects/{project_id}/methodology",
        json={
            "text": "Yöntem\nKesitsel çalışma.",
            "source_sha256": "b" * 64,
            "source_format": "docx",
            "original_name": "yontem.docx",
            "char_count": 24,
            "truncated": False,
        },
        headers=headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"attached": True}
```

- [ ] **Step 1b: Test yardımcısını yaz**

`test_methodology_endpoint.py` bugün proje yaratmıyor. Yardımcıyı `test_jobs.py`'nin proje kurulum deseninden kopyalayın (aynı fixture'ı iki dosyada tekrar yazmak yerine önce `test_jobs.py`'deki kurulum bloğunu okuyun; ölçülmemiş bir isim uydurmayın).

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_methodology_endpoint.py -q`
Expected: FAIL — `KeyError: 'text'` ve 404

- [ ] **Step 3: Write minimal implementation**

**Önce import satırını genişletin.** `[ÖLÇÜM 2026-08-24]` `app.py:28` bugün yalnızca
`from .methodology_intake import MethodologyIntakeError, extract_document` diyor;
`MethodologyDocument` ve `MAX_DOCUMENT_CHARS` **import edilmemiş** ve bu task ikisini de
kullanıyor. Aynı şekilde `from .projects import ...` satırına `attach_methodology`,
`read_methodology` eklenir.

```python
# app.py — istek modeli
class MethodologyPayload(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_format: str = Field(min_length=1, max_length=8)
    original_name: str = Field(min_length=1, max_length=255)
    char_count: int = Field(ge=0)
    truncated: bool = False


class ProjectRequest(BaseModel):
    source_path: str = Field(min_length=1)
    project_root: Optional[str] = None
    brief: StudyBrief
    methodology: Optional[MethodologyPayload] = None
```

```python
# app.py — extract yanıtına metin eklenir
        return {
            "source_sha256": document.source_sha256,
            "source_format": document.source_format,
            "original_name": Path(request.source_path).name,
            "char_count": document.char_count,
            "truncated": document.truncated,
            "text": document.text,
            "warnings": _merged_warnings(document.warnings, brief["warnings"]),
            "brief": brief,
        }
```

`original_name` yalnızca dosya **adı**dır, yolu değil — renderer'ın yolu görmeme garantisi (spec §3) korunur. `Path(...).name` bir dizin bileşeni döndüremez.

```python
# app.py — proje açıkken ekleme
    @v1.post("/projects/{project_id}/methodology")
    def attach_project_methodology(
        project_id: UUID, request: MethodologyPayload
    ) -> dict[str, bool]:
        context = _get_context(projects, project_id)
        with context.state_lock:
            document = MethodologyDocument(
                source_sha256=request.source_sha256,
                source_format=request.source_format,
                text=request.text,
                char_count=request.char_count,
                truncated=request.truncated,
                warnings=(),
            )
            attach_methodology(context.project, document, request.original_name)
            context.methodology = read_methodology(context.project)
            append_audit_event(
                context.project,
                {"type": "methodology_document_attached", "actor": "user"},
            )
        return {"attached": True}
```

```python
# projects.py — AUDIT_EVENT_TYPES'a ekle
        "methodology_document_attached",
```

`create_local_project` içinde, `create_project(...)` çağrısından hemen sonra:

```python
            if request.methodology is not None:
                attach_methodology(
                    project,
                    MethodologyDocument(
                        source_sha256=request.methodology.source_sha256,
                        source_format=request.methodology.source_format,
                        text=request.methodology.text,
                        char_count=request.methodology.char_count,
                        truncated=request.methodology.truncated,
                        warnings=(),
                    ),
                    request.methodology.original_name,
                )
                append_audit_event(
                    project, {"type": "methodology_document_attached", "actor": "user"}
                )
```

`ProjectContext`'e alan ekleyin ve `_restore_context` içinde doldurun — proje kapatılıp açıldığında belge kaybolmamalı:

```python
    methodology: "MethodologyRecord | None" = None
```

```python
    # _restore_context içinde, context kurulduktan sonra
    context.methodology = read_methodology(project)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
Expected: PASS (280 + yeni testler)

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/app.py services/analysis/biostat_service/projects.py services/analysis/tests/test_methodology_endpoint.py
git commit -m "feat: accept a methodology document when a project is created or open"
```

---

### Task 3: Renderer köprüsü — belge proje doğana kadar nerede durur

Bugün `extraction`, `StudyBrief.tsx:117`'de bileşenin **yerel** state'inde ve App'e hiç çıkmıyor; `DataIntake` onu göremiyor, proje yaratma çağrısı da göremiyor.

**Files:**
- Modify: `apps/desktop/src/api/types.ts`, `apps/desktop/src/api/client.ts`
- Modify: `apps/desktop/src/features/project/store.ts`, `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/features/study/StudyBrief.tsx`
- Modify: `apps/desktop/electron/api-proxy.ts`
- Test: `apps/desktop/src/features/study/StudyBrief.test.tsx`, `apps/desktop/electron/api-proxy.test.ts`

**Interfaces:**
- Consumes: Task 2'nin `text` + `original_name` alanları
- Produces:
  - `MethodologyExtraction` DTO'suna `text: string`, `original_name: string`
  - `store.ts`: `methodology: MethodologyExtraction | null` + `setMethodology(value)` action'ı
  - `client.ts`: `createProject`'in gövdesine `methodology` bloğu; yeni `attachMethodology(projectId, payload)`

- [ ] **Step 1: Write the failing test**

```tsx
// StudyBrief.test.tsx
it("lifts the extracted document out of the component", async () => {
  const onMethodology = vi.fn();
  const api = {
    selectMethodologyDocument: async () => "yontem.docx",
    extractMethodology: async () => ({
      source_sha256: "a".repeat(64),
      source_format: "docx",
      original_name: "yontem.docx",
      char_count: 24,
      truncated: false,
      text: "Yöntem\nKesitsel çalışma.",
      warnings: [],
      brief: { title: null, question: null, hypothesis: null, design: null, outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [] },
    }),
  };

  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} onMethodology={onMethodology} language="tr" api={api as never} />);
  await userEvent.click(screen.getByRole("button", { name: /belge/i }));

  await waitFor(() => expect(onMethodology).toHaveBeenCalledWith(
    expect.objectContaining({ text: "Yöntem\nKesitsel çalışma.", original_name: "yontem.docx" }),
  ));
});
```

```ts
// api-proxy.test.ts
it("allows attaching a methodology document to an open project", async () => {
  const proxy = createAuthenticatedApiProxy(session, request, capabilities);
  await expect(proxy({
    method: "POST",
    path: `/v1/projects/${uuid}/methodology`,
    body: { text: "Yöntem", source_sha256: "a".repeat(64), source_format: "docx", original_name: "y.docx", char_count: 6, truncated: false },
  })).resolves.toBeDefined();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:desktop`
Expected: FAIL — `onMethodology is not a function` ve `Invalid API request`

- [ ] **Step 3: Write minimal implementation**

```ts
// api-proxy.ts — API_CAPABILITIES dizisine
  { method: "POST", route: new RegExp(`^/v1/projects/${UUID}/methodology$`) },
```

Gövde enjeksiyonu **yoktur** — bu rota dosya yolu taşımaz, yalnızca metin taşır. `["source_path", "project_root", "destination"]` reddi zaten gövdeyi koruyor.

```tsx
// StudyBrief.tsx — yerel state korunur (rozet gösterimi için) ama yukarı da bildirilir
      const result = await api.extractMethodology();
      setExtraction(result);
      onMethodology?.(result);
```

```ts
// store.ts — reducer'a
  | { type: "methodology"; value: MethodologyExtraction | null }
// case:
    case "methodology": return { ...state, methodology: action.value };
```

**Dikkat — `clearDependents` tuzağı:** `store.ts:60`'ta `brief` action'ı `clearDependents` çağırıyor. Belge, brief'e bağımlı bir türev **değil**; brief değişince silinmemeli. `methodology` case'i `clearDependents` çağırmaz.

```ts
// client.ts — createProject gövdesine
      body: { ...payload, ...(methodology ? { methodology } : {}) },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:desktop && npm run typecheck --workspace apps/desktop`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop
git commit -m "feat: carry the extracted document from the brief step into the project"
```

---

### Task 4: Eşleştirme sözleşmesi — `ColumnSummary`, `RoleProposal`, protokol

Spec §5'in sözleşmesi bugün yalnızca yarısı kadar var (`Proposal`, `BriefProposal`). Eşleştirme tarafı hiç yok.

**Files:**
- Modify: `services/analysis/biostat_service/extractors/contracts.py`
- Test: `services/analysis/tests/test_contracts.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ColumnSummary: name: str; kind: str; unique_values: int; non_missing: int`
  - `@dataclass(frozen=True) class RoleProposal: column: str; role: Proposal | None; kind: Proposal | None`
  - `class MethodologyExtractor(Protocol)` — `name`, `available()`, `extract_brief()`, `match_variables()`
  - `column_summaries(profile: DataProfile) -> tuple[ColumnSummary, ...]`

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_contracts.py sonuna
import dataclasses

from biostat_service.extractors.contracts import ColumnSummary, RoleProposal


def test_column_summary_carries_no_cell_values() -> None:
    """Privacy is a type signature, not a policy (spec §5)."""
    fields = {field.name for field in dataclasses.fields(ColumnSummary)}
    assert fields == {"name", "kind", "unique_values", "non_missing"}


def test_role_proposal_may_carry_a_kind_correction_alone() -> None:
    proposal = RoleProposal(
        column="evre",
        role=None,
        kind=Proposal(value="categorical", confidence=0.7, source="rule"),
    )
    assert proposal.role is None
    assert proposal.kind is not None and proposal.kind.value == "categorical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_contracts.py -q`
Expected: FAIL — `ImportError: cannot import name 'ColumnSummary'`

- [ ] **Step 3: Write minimal implementation**

```python
# extractors/contracts.py
from typing import Protocol


@dataclass(frozen=True)
class ColumnSummary:
    """What an engine may know about one column.

    DELIBERATELY NO CELL VALUES (spec §5). If a cloud engine is ever enabled,
    patient data cannot travel because the type it would travel in has nowhere
    to put it. This is the privacy guarantee's load-bearing line; adding a
    `sample_values` field silently repeals it.
    """

    name: str
    kind: str
    unique_values: int
    non_missing: int


@dataclass(frozen=True)
class RoleProposal:
    """One column's proposed study role and/or corrected kind.

    Both fields are independently optional: a document routinely says what a
    column IS ("evre bir sınıflandırmadır" → kind) without saying what it DOES
    in the analysis (outcome/exposure/covariate → role), and vice versa.
    """

    column: str
    role: Proposal | None = None
    kind: Proposal | None = None


class MethodologyExtractor(Protocol):
    """Spec §5's engine contract. RuleExtractor is the always-available floor."""

    name: str

    def available(self) -> bool: ...

    def extract_brief(self, document: "MethodologyDocument") -> BriefProposal: ...

    def match_variables(
        self,
        document: "MethodologyDocument",
        concepts: BriefProposal,
        columns: tuple[ColumnSummary, ...],
    ) -> tuple[RoleProposal, ...]: ...
```

```python
# extractors/contracts.py — profil dönüştürücü
def column_summaries(profile: "DataProfile") -> tuple[ColumnSummary, ...]:
    """Project a DataProfile down to what engines may see. Stable order."""
    return tuple(
        ColumnSummary(
            name=name,
            kind=metadata.kind,
            unique_values=metadata.unique_values,
            non_missing=metadata.non_missing,
        )
        for name, metadata in sorted(profile.variables.items())
    )
```

`sorted(...)` **determinizm içindir**, kozmetik değil: sözlük sırası girdi dosyasının sütun sırasına bağlıdır ve eşleştirme skorları eşitlendiğinde sıra kazananı belirler (Global Constraints: stabil tie-break).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/extractors/contracts.py services/analysis/tests/test_contracts.py
git commit -m "feat: define the variable-matching contract without cell values"
```

---

### Task 5: Kavram çıkarımı — eşleştirilecek bir şey olması

**Bu task, planın ilk taslağında YOKTU ve eksikliği planı çalışmaz kılıyordu.** `[ÖLÇÜM 2026-08-24]` `RuleExtractor.extract_brief` (`rule.py:85-91`) yalnızca `design` dolduruyor; `outcome_concepts`, `exposure_concepts`, `covariate_concepts` **boş tuple** olarak dönüyor. Task 6'nın `match_variables`'ı boş bir listeyi eşleştirmeye çalışırdı ve hiçbir zaman hiçbir şey önermezdi — testleri de yeşil geçerdi, çünkü "hiçbir öneri yok" geçerli bir çıktıdır. STATE.md 0c bunu zaten söylüyordu: *"asıl ayırt edici, kural motorunun neredeyse hiç yapamadığı kavram çıkarımı."*

**Files:**
- Modify: `services/analysis/biostat_service/extractors/rule.py`
- Test: `services/analysis/tests/test_rule_extractor.py`

**Interfaces:**
- Produces: `BriefProposal.outcome_concepts / exposure_concepts / covariate_concepts` dolu döner

**Ölçüm durumu — dürüstçe:** bu task'ın çıkarım kalitesi **ölçülmedi** ve bu planda ölçülemez; gold set Plan 3'te kuruluyor (STATE.md 0c). Burada kurulan şey bir **taban çizgisi**: LLM'in ne kattığını ölçecek olan referans. Kalıpların dar tutulması bilinçli — Plan 1'de ölçülen ders, geniş kalıbın başka bir çalışmadan yapılan alıntıyı kendi beyanı sanmasıydı.

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_rule_extractor.py sonuna
def test_extracts_a_primary_outcome_concept() -> None:
    document = _document(
        "Yöntem\nBirincil sonlanım 30 günlük mortalite olarak tanımlandı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [proposal.value for proposal in brief.outcome_concepts] == [
        "30 günlük mortalite"
    ]
    assert brief.outcome_concepts[0].evidence is not None


def test_extracts_a_covariate_list() -> None:
    document = _document(
        "Yöntem\nModeller yaş, cinsiyet ve vücut kitle indeksi için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [proposal.value for proposal in brief.covariate_concepts] == [
        "yaş",
        "cinsiyet",
        "vücut kitle indeksi",
    ]


def test_a_sentence_without_a_concept_pattern_yields_nothing() -> None:
    document = _document("Yöntem\nVeriler SPSS 26 ile analiz edildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.outcome_concepts == ()
    assert brief.covariate_concepts == ()
```

`_document(...)` yardımcısı `test_rule_extractor.py`'de zaten var; **yeniden yazmayın**, mevcut olanı kullanın (yoksa dosyanın kendi kurulum desenini izleyin).

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_rule_extractor.py -q`
Expected: FAIL — `assert [] == ['30 günlük mortalite']`

- [ ] **Step 3: Write minimal implementation**

```python
# extractors/rule.py
# Kavram kalıpları. Her kalıp, ARDINDAN gelen metnin kavram olduğunu iddia
# eder. Kalıplar dar: "sonuç" tek başına yok (Türkçe'de "sonuç olarak" bağlacı
# her metodoloji metninde geçer ve her seferinde yanlış eşleşirdi).
CONCEPT_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "outcome",
        r"(?:birincil|primer|ana)\s+(?:sonlan[ıi]m|son\s+nokta|[çc][ıi]kt[ıi])"
        r"|primary\s+(?:outcome|endpoint)|ba[ğg][ıi]ml[ıi]\s+de[ğg]i[şs]ken",
    ),
    (
        "exposure",
        r"maruziyet|ba[ğg][ıi]ms[ıi]z\s+de[ğg]i[şs]ken|exposure(?:\s+variable)?",
    ),
    (
        "covariate",
        r"kovaryat|covariates?|d[üu]zeltil(?:di|erek|mi[şs])|adjusted\s+for"
        r"|kar[ıi][şs]t[ıi]r[ıi]c[ıi]|confounder",
    ),
)

# Kalıptan sonra kavramı taşıyan bağlantı sözcükleri. Bunlardan biri yoksa
# cümle ayrıştırılmaz — kalıp eşleşse bile boş dönülür (uydurma yasak).
_CONNECTORS = re.compile(
    r"\b(?:olarak\s+tan[ıi]mland[ıi]|olarak\s+belirlendi|olarak|i[çc]in|for|was|were|:)\b|\s+",
    re.IGNORECASE,
)
_SPLIT = re.compile(r",|\bve\b|\band\b|\bile\b", re.IGNORECASE)
_TRAILING = re.compile(r"\s*(?:i[çc]in\s+)?d[üu]zeltil\w*|\s*olarak\s+\w+|\s*[.;]\s*$", re.IGNORECASE)

# Bir kavram adı için makul uzunluk penceresi. Alt sınır: tek harfli parçalar
# ayrıştırma artığıdır. Üst sınır: 60 karakteri aşan bir parça artık bir
# değişken adı değil, cümlenin geri kalanıdır.
CONCEPT_MIN_CHARS = 2
CONCEPT_MAX_CHARS = 60
```

```python
    def _concepts(self, text: str, pattern: str) -> tuple[Proposal, ...]:
        """Extract concept names that follow one pattern, or nothing at all."""
        found: list[Proposal] = []
        seen: set[str] = set()
        for match in re.finditer(pattern, text, re.IGNORECASE):
            sentence = self._sentence_around(text, match.start())
            tail = text[match.end():match.end() + CONCEPT_MAX_CHARS * 4]
            tail = tail.split(".")[0]
            for raw in _SPLIT.split(tail):
                candidate = _TRAILING.sub("", raw).strip(" \t:,–—-")
                if not CONCEPT_MIN_CHARS <= len(candidate) <= CONCEPT_MAX_CHARS:
                    continue
                if candidate.lower() in seen:
                    continue
                seen.add(candidate.lower())
                found.append(
                    Proposal(
                        value=candidate,
                        confidence=RULE_CONFIDENCE,
                        source=self.name,
                        evidence=sentence[:EVIDENCE_MAX_CHARS],
                        evidence_offset=match.start(),
                    )
                )
        return tuple(found)
```

`extract_brief` genişletilir:

```python
        return BriefProposal(
            design=self._design(document.text, selected),
            outcome_concepts=self._concepts(selected, CONCEPT_PATTERNS[0][1]),
            exposure_concepts=self._concepts(selected, CONCEPT_PATTERNS[1][1]),
            covariate_concepts=self._concepts(selected, CONCEPT_PATTERNS[2][1]),
            warnings=warnings,
        )
```

**Uyarı — bu adımın en olası kusuru:** ayrıştırma cümlenin geri kalanını kavram sanmak. Testlerin üçüncüsü (`_a_sentence_without_a_concept_pattern_yields_nothing`) tam olarak bunu kolluyor; geçmiyorsa kalıbı **genişletmeyin, daraltın**.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
Expected: PASS — mevcut `test_rule_extractor.py` testleri dahil (regresyon: `design` çıkarımı değişmemeli)

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/extractors/rule.py services/analysis/tests/test_rule_extractor.py
git commit -m "feat: extract outcome, exposure and covariate concepts from the document"
```

---

### Task 6: Bulanık eşleştirme çekirdeği ve `RuleExtractor.match_variables`

**Files:**
- Create: `services/analysis/biostat_service/extractors/matching.py`
- Modify: `services/analysis/biostat_service/extractors/rule.py`
- Test: `services/analysis/tests/test_variable_matching.py` (yeni), `test_rule_extractor.py`

**Interfaces:**
- Consumes: `ColumnSummary`, `RoleProposal`, `Proposal` (Task 4) · dolu kavram listeleri taşıyan `BriefProposal` (Task 5)
- Produces:
  - `normalize(label: str) -> str`
  - `similarity(concept: str, column: str) -> float`
  - `best_column(concept: str, columns: tuple[ColumnSummary, ...]) -> tuple[str, float] | None`
  - `RuleExtractor.match_variables(...)`

**Eşik kararı — kalibre edilmemiş, gerekçesi ile:** `MATCH_THRESHOLD = 0.80`. Bu sayı **ölçülmedi** (`doğrulanmadı`); gold set Plan 3'te kuruluyor. Yanlış olmasının bedeli asimetrik ve bilinçli o yöne eğildi: eşiğin **altındaki** her eşleşme "düşük güven" bloğuna düşer, toplu kabul düğmesinin dışında kalır ve kullanıcıya tek tek sorulur (spec §6). Yani eşik fazla yüksekse sonuç *daha çok soru*, fazla düşükse *sessizce yanlış rol*. Yükseğe eğmek fail-safe yön. Plan 3 ölçümünden sonra bu satır güncellenmeli.

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_variable_matching.py
"""Behavioral coverage for concept-to-column matching."""

from __future__ import annotations

from biostat_service.extractors.contracts import ColumnSummary
from biostat_service.extractors.matching import best_column, normalize, similarity


def _columns(*names: str) -> tuple[ColumnSummary, ...]:
    return tuple(
        ColumnSummary(name=name, kind="continuous", unique_values=9, non_missing=90)
        for name in names
    )


def test_turkish_folding_survives_dotted_capital_i() -> None:
    assert normalize("İlaç Dozu") == normalize("ilac_dozu")


def test_separators_and_case_do_not_change_a_label() -> None:
    assert normalize("Sistolik KB") == normalize("sistolik kb")
    assert normalize("HbA1c") == normalize("hba1c")


def test_an_abbreviation_matches_its_spelled_out_column() -> None:
    columns = _columns("sistolik_kan_basinci", "yas", "cinsiyet")
    match = best_column("sistolik KB", columns)
    assert match is not None
    assert match[0] == "sistolik_kan_basinci"


def test_an_unrelated_concept_matches_nothing() -> None:
    assert best_column("serum kreatinin", _columns("yas", "cinsiyet")) is None


def test_ties_break_alphabetically_for_determinism() -> None:
    columns = _columns("beta", "alpha")
    first = best_column("gamma_xyz", columns)
    second = best_column("gamma_xyz", columns)
    assert first == second


def test_similarity_is_symmetric_enough_to_be_stable() -> None:
    assert similarity("yaş", "yas") > 0.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_variable_matching.py -q`
Expected: FAIL — `ModuleNotFoundError: biostat_service.extractors.matching`

- [ ] **Step 3: Write minimal implementation**

```python
# services/analysis/biostat_service/extractors/matching.py
"""Deterministic concept-to-column matching.

No new dependency: difflib is stdlib and its ratio is deterministic across
runs and platforms, which the plan digest requires. rapidfuzz would be faster
and is not needed — a study has tens of columns, not millions.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

from .contracts import ColumnSummary

# Türkçe katlama. `İ`.lower() iki kod noktasına açılır (i + U+0307) — bu tam
# olarak Plan 1'de ölçülen ve bölüm başlıklarını kaçıran hatanın kaynağıydı
# (STATE.md madde 0). Katlamayı lower()'dan ÖNCE, açık bir tabloyla yapıyoruz.
_FOLD = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
    }
)
_SEPARATORS = re.compile(r"[\s_\-.]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")

# Klinik kısaltma sözlüğü (spec §5). Genişletilebilir; her giriş TEK yönlüdür:
# kısaltma → açık hâli. Ters yön normalizasyonla zaten yakalanıyor.
ABBREVIATIONS: dict[str, str] = {
    "kb": "kanbasinci",
    "ta": "kanbasinci",
    "skb": "sistolikkanbasinci",
    "dkb": "diyastolikkanbasinci",
    "vki": "vucutkitleindeksi",
    "bmi": "vucutkitleindeksi",
    "kkh": "koronerkalphastaligi",
    "dm": "diyabetesmellitus",
    "ht": "hipertansiyon",
    "egfr": "glomerulerfiltrasyonhizi",
    "hba1c": "hba1c",
}

MATCH_THRESHOLD = 0.80


def normalize(label: str) -> str:
    """Fold one label to a comparable key: Turkish-safe, separator-free."""
    folded = unicodedata.normalize("NFC", label).translate(_FOLD).lower()
    expanded = " ".join(
        ABBREVIATIONS.get(token, token) for token in _SEPARATORS.split(folded) if token
    )
    return _NON_ALNUM.sub("", expanded)


def similarity(concept: str, column: str) -> float:
    """Deterministic 0..1 similarity between one concept and one column name."""
    left, right = normalize(concept), normalize(column)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    # Bir kavramın sütun adının İÇİNDE geçmesi (ya da tersi) gerçek bir
    # eşleşmedir ama SequenceMatcher uzunluk farkı yüzünden bunu cezalandırır:
    # "yas" ile "hastanin_yasi" arasında ratio düşük çıkar. İçerme durumunda
    # taban skor veriyoruz, ve ratio daha yüksekse onu bırakıyoruz.
    containment = 0.85 if left in right or right in left else 0.0
    return max(containment, SequenceMatcher(None, left, right).ratio())


def best_column(
    concept: str, columns: tuple[ColumnSummary, ...]
) -> tuple[str, float] | None:
    """Return the best-scoring column above MATCH_THRESHOLD, or None.

    Ties break on the column name so the same document and workbook always
    produce the same plan digest (Global Constraints).
    """
    scored = sorted(
        ((similarity(concept, column.name), column.name) for column in columns),
        key=lambda item: (-item[0], item[1]),
    )
    if not scored or scored[0][0] < MATCH_THRESHOLD:
        return None
    score, name = scored[0]
    return name, score
```

```python
# extractors/rule.py — RuleExtractor'a
    def match_variables(
        self,
        document: MethodologyDocument,
        concepts: BriefProposal,
        columns: tuple[ColumnSummary, ...],
    ) -> tuple[RoleProposal, ...]:
        """Map extracted concepts onto workbook columns. Silence over guessing."""
        proposals: dict[str, RoleProposal] = {}
        for role, group in (
            ("outcome", concepts.outcome_concepts),
            ("exposure", concepts.exposure_concepts),
            ("covariate", concepts.covariate_concepts),
        ):
            for concept in group:
                match = best_column(concept.value, columns)
                if match is None or match[0] in proposals:
                    continue
                name, score = match
                proposals[name] = RoleProposal(
                    column=name,
                    role=Proposal(
                        value=role,
                        confidence=score,
                        source=self.name,
                        evidence=concept.evidence,
                        evidence_offset=concept.evidence_offset,
                    ),
                )
        return tuple(proposals[name] for name in sorted(proposals))
```

`match[0] in proposals` kontrolü **ilk gelen kazanır** demektir ve sıra `outcome → exposure → covariate`'tır: bir sütun hem sonuç hem kovaryat olamaz, ve sonuç değişkeni yanlış atanırsa `planner` bloke olur — en pahalı hatayı en önce yerleştirmek doğru sıralama.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/extractors services/analysis/tests/test_variable_matching.py
git commit -m "feat: match methodology concepts onto workbook columns deterministically"
```

---

### Task 7: Doküman kaynaklı `kind` düzeltmesi ve çelişki tespiti

Bulgu A-2'nin kalbi: `evre`(1-4) veri tarafından `continuous` sayılıyor; belge onun bir sınıflandırma olduğunu söylüyor.

**Files:**
- Modify: `services/analysis/biostat_service/extractors/rule.py`
- Create: `services/analysis/biostat_service/variable_reconciliation.py`
- Test: `services/analysis/tests/test_variable_reconciliation.py` (yeni)

**Interfaces:**
- Consumes: `RoleProposal` (Task 4), `match_variables` çıktısı (Task 6), `DataProfile`
- Produces:
  - `@dataclass(frozen=True) class Conflict: column: str; data_kind: str; document_kind: str; evidence: str | None; evidence_offset: int | None`
  - `detect_conflicts(profile: DataProfile, proposals: tuple[RoleProposal, ...]) -> tuple[Conflict, ...]`

**Tek yönlü düzeltme kuralı (spec §5):** belge yalnızca *"bu sayısal sütun aslında kategoriktir"* diyebilir. Ters yön (`categorical` → `continuous`) **kabul edilmez**: veri, bir sütunda kaç benzersiz değer olduğu konusunda yalan söylemez, ama bir belge "sürekli ölçüm" ifadesini metaforik kullanabilir. Kuralı tek yönlü tutmak, yanlış çıkarımın veriyi bozmasını yapısal olarak engeller.

- [ ] **Step 1: Write the failing test**

```python
# services/analysis/tests/test_variable_reconciliation.py
"""Behavioral coverage for data-versus-document conflict detection."""

from __future__ import annotations

from biostat_service.data_intake import DataProfile, VariableMetadata
from biostat_service.extractors.contracts import Proposal, RoleProposal
from biostat_service.variable_reconciliation import detect_conflicts


def _profile(kind: str) -> DataProfile:
    return DataProfile(
        source_path=__import__("pathlib").Path("unused.xlsx"),
        source_sha256="a" * 64,
        sheets=("Analysis",),
        selected_sheet="Analysis",
        rows=100,
        columns=1,
        missing_cells=0,
        variables={
            "evre": VariableMetadata(
                source_label="evre",
                original_name="evre",
                display_name="Evre",
                kind=kind,
                non_missing=100,
                missing=0,
                unique_values=4,
            )
        },
        warnings=(),
    )


def _categorical_claim() -> tuple[RoleProposal, ...]:
    return (
        RoleProposal(
            column="evre",
            kind=Proposal(
                value="categorical",
                confidence=0.7,
                source="rule",
                evidence="Hastalar TNM evresine göre I-IV olarak sınıflandırıldı.",
                evidence_offset=120,
            ),
        ),
    )


def test_numeric_column_claimed_categorical_is_a_conflict() -> None:
    conflicts = detect_conflicts(_profile("continuous"), _categorical_claim())
    assert len(conflicts) == 1
    assert conflicts[0].column == "evre"
    assert conflicts[0].data_kind == "continuous"
    assert conflicts[0].document_kind == "categorical"
    assert conflicts[0].evidence is not None


def test_agreement_is_not_a_conflict() -> None:
    assert detect_conflicts(_profile("categorical"), _categorical_claim()) == ()


def test_the_document_may_not_turn_a_category_into_a_measurement() -> None:
    claim = (
        RoleProposal(
            column="evre",
            kind=Proposal(value="continuous", confidence=0.9, source="rule"),
        ),
    )
    assert detect_conflicts(_profile("categorical"), claim) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_variable_reconciliation.py -q`
Expected: FAIL — `ModuleNotFoundError: biostat_service.variable_reconciliation`

- [ ] **Step 3: Write minimal implementation**

```python
# services/analysis/biostat_service/variable_reconciliation.py
"""Compare what the data says about a column with what the document says.

This module never decides. It reports a disagreement and — in Task 7 — what
that disagreement costs, so the user can decide (spec §6).
"""

from __future__ import annotations

from dataclasses import dataclass

from .data_intake import DataProfile
from .extractors.contracts import RoleProposal

# Belgenin veriyi düzeltmesine izin verilen TEK yön (spec §5).
ALLOWED_CORRECTIONS: frozenset[tuple[str, str]] = frozenset(
    {("continuous", "categorical"), ("continuous", "binary")}
)


@dataclass(frozen=True)
class Conflict:
    column: str
    data_kind: str
    document_kind: str
    evidence: str | None
    evidence_offset: int | None


def detect_conflicts(
    profile: DataProfile, proposals: tuple[RoleProposal, ...]
) -> tuple[Conflict, ...]:
    """Report every column the document contradicts, in stable column order."""
    conflicts: list[Conflict] = []
    for proposal in sorted(proposals, key=lambda item: item.column):
        if proposal.kind is None or proposal.column not in profile.variables:
            continue
        data_kind = profile.variables[proposal.column].kind
        document_kind = proposal.kind.value
        if data_kind == document_kind:
            continue
        if (data_kind, document_kind) not in ALLOWED_CORRECTIONS:
            continue
        conflicts.append(
            Conflict(
                column=proposal.column,
                data_kind=data_kind,
                document_kind=document_kind,
                evidence=proposal.kind.evidence,
                evidence_offset=proposal.kind.evidence_offset,
            )
        )
    return tuple(conflicts)
```

```python
# extractors/rule.py — kind iddiası üreten kalıplar
# Bir sütunun ADI cümlede geçiyor ve cümle sınıflandırma dili taşıyorsa,
# belge o sütun için "kategorik" iddiasında bulunuyordur. Kalıplar DAR
# tutuldu: Plan 1'de ölçülen ders (STATE.md 0c bulgu 3), geniş kalıbın
# başka bir çalışmadan yapılan ALINTIYI kendi beyanı sanmasıydı.
CATEGORICAL_CLAIM = re.compile(
    r"(sınıfland[ıi]r|gruplan?d[ıi]r|kategori|evrele(?:me|ndi)|"
    r"classified|categori[sz]ed|grouped into|stratified)",
    re.IGNORECASE,
)
```

`match_variables` içinde, rol ataması yapıldıktan sonra her sütun adı için `document.text` taranır; adı geçen cümle `CATEGORICAL_CLAIM` içeriyorsa `RoleProposal.kind` doldurulur. Cümle çıkarımı için mevcut `RuleExtractor._sentence_around` (`rule.py:136`) yeniden kullanılır — yeni cümle bölücü yazılmaz.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/variable_reconciliation.py services/analysis/biostat_service/extractors/rule.py services/analysis/tests/test_variable_reconciliation.py
git commit -m "feat: detect where the document contradicts the data about a column"
```

---

### Task 8: Çelişkinin bedeli — `planner`'a iki kez sordurmak

Spec §6'nın kalbi: alt satırdaki metotlar LLM tahmini değil, `planner.py`'nin iki farklı girdiyle verdiği **gerçek** cevabı. Kullanıcının istatistik bilmesi gerekmez; seçimin bedelini, analizi çalıştıracak kodun kendisi söyler.

**Files:**
- Modify: `services/analysis/biostat_service/variable_reconciliation.py`
- Modify: `services/analysis/biostat_service/app.py`
- Test: `services/analysis/tests/test_variable_reconciliation.py`, `services/analysis/tests/test_methodology_endpoint.py`

**Interfaces:**
- Consumes: `Conflict` (Task 7), `planner.build_plan` (**salt okunur — dosyaya dokunulmaz**)
- Produces:
  - `@dataclass(frozen=True) class ConflictCost: column, data_kind, document_kind, evidence, evidence_offset, methods_if_document: tuple[str, ...], methods_if_data: tuple[str, ...], blocked_if_document: tuple[str, ...], blocked_if_data: tuple[str, ...]`
  - `price_conflicts(brief, profile, roles, conflicts) -> tuple[ConflictCost, ...]`
  - `POST /v1/projects/{project_id}/variable-proposals` → `{"proposals": [...], "conflicts": [...]}`

- [ ] **Step 1: Write the failing test**

```python
# test_variable_reconciliation.py sonuna
from biostat_service.contracts import StudyBrief, VariableRole
from biostat_service.variable_reconciliation import price_conflicts


def test_the_two_choices_are_priced_by_the_planner_itself() -> None:
    profile = _profile_with_outcome()  # bkz. Step 1b
    brief = StudyBrief(
        title="Evre ve sağkalım",
        question="Evre ile sonuç arasında ilişki var mı?",
        hypothesis="İleri evre daha kötü sonuçla ilişkilidir.",
        design="cohort",
        outcome_variables=["sonuc"],
        exposure_variables=["evre"],
    )
    roles = {
        "sonuc": VariableRole(name="sonuc", role="outcome", kind="continuous", confirmed=False),
        "evre": VariableRole(name="evre", role="exposure", kind="continuous", confirmed=False),
    }
    conflicts = detect_conflicts(profile, _categorical_claim())

    costs = price_conflicts(brief, profile, roles, conflicts)

    assert len(costs) == 1
    cost = costs[0]
    # İki seçenek GERÇEKTEN farklı analiz üretmeli; aynıysa kullanıcıya
    # gösterilecek bir bedel yoktur ve bu testin varlık sebebi kalmaz.
    assert cost.methods_if_document != cost.methods_if_data
    assert all(isinstance(method, str) for method in cost.methods_if_document)


def test_pricing_never_mutates_the_caller_roles() -> None:
    profile = _profile_with_outcome()
    roles = {
        "evre": VariableRole(name="evre", role="exposure", kind="continuous", confirmed=False),
    }
    snapshot = {name: role.model_copy() for name, role in roles.items()}

    price_conflicts(_brief(), profile, roles, detect_conflicts(profile, _categorical_claim()))

    assert roles["evre"].kind == snapshot["evre"].kind
```

- [ ] **Step 1b: Fixture'ı yaz**

`_profile_with_outcome()`, `evre` (4 benzersiz, `continuous`) ve `sonuc` (sürekli) taşıyan bir `DataProfile` döndürür. `_profile()` yardımcısını genişletin; **yeni bir fixture dosyası yaratmayın**, aynı desende ikinci sütun ekleyin.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests/test_variable_reconciliation.py -q`
Expected: FAIL — `cannot import name 'price_conflicts'`

- [ ] **Step 3: Write minimal implementation**

```python
# variable_reconciliation.py
from .contracts import AnalysisPlan, StudyBrief, VariableRole
from .planner import build_plan


@dataclass(frozen=True)
class ConflictCost:
    """One disagreement, priced in the analyses it would actually produce."""

    column: str
    data_kind: str
    document_kind: str
    evidence: str | None
    evidence_offset: int | None
    methods_if_document: tuple[str, ...]
    methods_if_data: tuple[str, ...]
    blocked_if_document: tuple[str, ...]
    blocked_if_data: tuple[str, ...]


def _plan_for(
    brief: StudyBrief,
    profile: DataProfile,
    roles: dict[str, VariableRole],
    column: str,
    kind: str,
) -> AnalysisPlan:
    """Build a plan with ONE column's kind overridden, without mutating input.

    model_copy(update=...) is required, not cosmetic: VariableRole is a pydantic
    model shared with the caller's live state. Mutating it here would silently
    change the roles the user is still deciding about.
    """
    candidate = {
        name: (role.model_copy(update={"kind": kind}) if name == column else role)
        for name, role in roles.items()
    }
    return build_plan(brief, profile, candidate)


def price_conflicts(
    brief: StudyBrief,
    profile: DataProfile,
    roles: dict[str, VariableRole],
    conflicts: tuple[Conflict, ...],
) -> tuple[ConflictCost, ...]:
    """Ask the planner what each choice costs. The planner is the authority.

    Nothing here predicts a method name. build_plan is the same function that
    will run the analysis, so what the user is shown is what they will get.
    """
    priced: list[ConflictCost] = []
    for conflict in conflicts:
        with_document = _plan_for(
            brief, profile, roles, conflict.column, conflict.document_kind
        )
        with_data = _plan_for(brief, profile, roles, conflict.column, conflict.data_kind)
        priced.append(
            ConflictCost(
                column=conflict.column,
                data_kind=conflict.data_kind,
                document_kind=conflict.document_kind,
                evidence=conflict.evidence,
                evidence_offset=conflict.evidence_offset,
                methods_if_document=tuple(item.method for item in with_document.items),
                methods_if_data=tuple(item.method for item in with_data.items),
                blocked_if_document=tuple(with_document.blocking_errors),
                blocked_if_data=tuple(with_data.blocking_errors),
            )
        )
    return tuple(priced)
```

**`planner.py` değişmez.** Bu modül onu yalnızca **çağırır**. `build_plan` imzasında doküman metni, LLM çıktısı veya güven skoru yoktur ve bu planda da olmayacaktır (spec §3).

Bu endpoint dört yeni isim kullanıyor; import satırlarını genişletin:
`RuleExtractor` (`.extractors.rule`), `column_summaries` (`.extractors.contracts`),
`detect_conflicts` ve `price_conflicts` (`.variable_reconciliation`).

```python
# app.py — öneri + çelişki endpoint'i
    @v1.post("/projects/{project_id}/variable-proposals")
    def variable_proposals(project_id: UUID) -> dict[str, Any]:
        context = _get_context(projects, project_id)
        if context.methodology is None:
            return {"proposals": [], "conflicts": []}
        document = MethodologyDocument(
            source_sha256=context.methodology.source_sha256,
            source_format=context.methodology.source_format,
            text=context.methodology.text,
            char_count=context.methodology.char_count,
            truncated=context.methodology.truncated,
            warnings=(),
        )
        engine = RuleExtractor()
        concepts = engine.extract_brief(document)
        proposals = engine.match_variables(
            document, concepts, column_summaries(context.profile)
        )
        roles = _proposed_roles(context, proposals)
        conflicts = price_conflicts(
            context.brief,
            context.profile,
            roles,
            detect_conflicts(context.profile, proposals),
        )
        return {
            "proposals": [_role_proposal_payload(item) for item in proposals],
            "conflicts": [_conflict_payload(item) for item in conflicts],
        }
```

`_proposed_roles`, `_role_proposal_payload`, `_conflict_payload` bu task'ta yazılır; `_proposal_payload` (`app.py:287`) deseni birebir izlenir — `evidence` serileştirmesindeki `EVIDENCE_MAX_CHARS` tavanı orada uygulanıyor ve **atlanmamalıdır** (gizlilik sınırı, STATE.md 0b).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
Expected: PASS

- [ ] **Step 5: api-proxy allowlist'i genişlet**

```ts
// api-proxy.ts
  { method: "POST", route: new RegExp(`^/v1/projects/${UUID}/variable-proposals$`) },
```

- [ ] **Step 6: Commit**

```bash
git add services/analysis apps/desktop/electron/api-proxy.ts
git commit -m "feat: price each conflict with the planner that will run the analysis"
```

---

### Task 9: `confirmed` bayrağının anlamını geri vermek ve toplu kabul

Bulgu A-1. STATE.md 0e'nin ölçümü: **sunucu kapısı zaten var** (`app.py:386` `not role.confirmed` → 422). Eksik olan yalnızca UI'ın kapıyı atlaması.

**Files:**
- Modify: `apps/desktop/src/features/data/DataIntake.tsx`
- Test: `apps/desktop/src/features/data/DataIntake.test.tsx`

**Interfaces:**
- Consumes: Task 8'in `proposals` + `conflicts` yükü
- Produces: `confirmed` yalnızca insan eylemiyle `true` olur; "Kalan N değişkeni kabul et" düğmesi

**Kural (spec §6):** `confirmed: false` → makine önerdi, insan bakmadı. `confirmed: true` → **insan gördü ve onayladı**. Toplu kabul düğmesi çelişkili ve düşük güvenli değişkenleri **kapsamaz**.

- [ ] **Step 1: Write the failing test**

```tsx
// DataIntake.test.tsx
it("does not mark machine-proposed roles as confirmed", async () => {
  const onApproval = vi.fn().mockResolvedValue(undefined);
  renderIntake({ onApproval });          // mevcut yardımcı
  await importWorkbook();                // mevcut yardımcı

  await userEvent.click(screen.getByRole("button", { name: /onayla/i }));

  expect(onApproval).not.toHaveBeenCalled();
});

it("confirms only the columns the bulk button covers", async () => {
  const onApproval = vi.fn().mockResolvedValue(undefined);
  renderIntake({ onApproval, conflicts: [conflictOn("evre")] });
  await importWorkbook();

  await userEvent.click(screen.getByRole("button", { name: /kalan/i }));

  const submitted = onApproval.mock.calls.at(-1)?.[0] ?? [];
  expect(submitted.find((role) => role.name === "evre")?.confirmed).toBe(false);
  expect(submitted.find((role) => role.name === "yas")?.confirmed).toBe(true);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:desktop`
Expected: FAIL — her rol `confirmed: true` geldiği için ilk test onaylamayı çağırır

- [ ] **Step 3: Write minimal implementation**

`DataIntake.tsx:81`'deki `confirmed: true` → `confirmed: false`. Rol/tür `select`'lerinin `onChange`'i (satır 121-122) `confirmed: true` yazmaya devam eder — **orası gerçek bir insan eylemidir**, doğruydu.

Toplu kabul:

```tsx
const bulkAcceptable = (name: string): boolean =>
  !conflicts.some((conflict) => conflict.column === name)
  && (proposals[name]?.confidence ?? 1) >= LOW_CONFIDENCE;

const acceptRemaining = () => {
  setRoles((current) => Object.fromEntries(
    Object.entries(current).map(([name, role]) => [
      name,
      bulkAcceptable(name) ? { ...role, confirmed: true } : role,
    ]),
  ));
};
```

Onay düğmesi, `confirmed: false` kalan bir değişken varken **disabled**. Bu, sunucunun 422'sini kullanıcıya hata olarak göstermek yerine önce engeller; sunucu kapısı ikinci savunma hattı olarak yerinde kalır.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:desktop && npm run typecheck --workspace apps/desktop`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/features/data
git commit -m "fix: let confirmed mean a human looked at the variable"
```

---

### Task 10: Onay ekranı — çelişki bloğu, kanıt ve rozetler

Spec §6 "Ekranlar": çelişkili ve düşük güvenli değişkenler listenin **üstünde ayrı blokta**; gerisi normal listede, önerileri ve kanıtlarıyla.

**Files:**
- Modify: `apps/desktop/src/features/data/DataIntake.tsx`
- Modify: `apps/desktop/src/features/study/StudyBrief.tsx` (rozet düşme kuralı)
- Test: `apps/desktop/src/features/data/DataIntake.test.tsx`, `StudyBrief.test.tsx`

**Interfaces:**
- Consumes: Task 8 yükü, Task 9 `confirmed` semantiği

- [ ] **Step 1: Write the failing test**

```tsx
// DataIntake.test.tsx
it("shows what each choice costs, in the planner's own words", async () => {
  renderIntake({ conflicts: [{
    column: "evre",
    data_kind: "continuous",
    document_kind: "categorical",
    evidence: "Hastalar TNM evresine göre I-IV olarak sınıflandırıldı.",
    evidence_offset: 120,
    methods_if_document: ["welch_anova"],
    methods_if_data: ["pearson_correlation"],
    blocked_if_document: [],
    blocked_if_data: [],
  }] });
  await importWorkbook();

  expect(screen.getByText(/welch/i)).toBeInTheDocument();
  expect(screen.getByText(/pearson/i)).toBeInTheDocument();
  expect(screen.getByText(/TNM evresine göre/)).toBeInTheDocument();
});
```

```tsx
// StudyBrief.test.tsx
it("drops the from-document badge once the user edits the field", async () => {
  renderBriefWithExtraction();     // design önerisi dolu gelir
  expect(screen.getByText(/dokümandan/i)).toBeInTheDocument();

  await userEvent.selectOptions(screen.getByLabelText(/tasarım/i), "trial");

  expect(screen.queryByText(/dokümandan/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:desktop`
Expected: FAIL — çelişki bloğu ve rozet düşme kuralı yok

- [ ] **Step 3: Write minimal implementation**

Çelişki bloğu, değişken listesinin **üstünde**, `role="group"` ile ve spec §6'daki metin düzeninde: veri ne diyor · belge ne diyor (kanıt cümlesi) · öneri · **bu seçim analizi değiştirir** satırı · iki düğme. `blocked_if_*` boş değilse o seçenek "bu seçim analizi engelliyor" olarak işaretlenir ve engel kodu gösterilir.

Metot adları kullanıcıya ham `method` kimliğiyle gösterilmez; `PlanReview.tsx`'in mevcut metot etiket sözlüğü yeniden kullanılır — **yeni bir sözlük yazılmaz**, ikisi ayrışırsa aynı analiz iki ekranda iki farklı adla görünür.

Rozet düşme kuralı (spec §6): `StudyBrief.tsx` her alan için `fromDocument: Set<keyof StudyBriefDto>` tutar; `update(key, ...)` çağrıldığında `key` bu kümeden çıkarılır. `.proposal-badge` yalnızca `fromDocument.has(key) && proposal.evidence` iken render edilir — STATE.md 0b'deki "`design` doğruyken `evidence` null olsa da rozet render ediliyor" borcu **burada kapanır**.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:desktop && npm run typecheck --workspace apps/desktop`
Expected: PASS

- [ ] **Step 5: Tam kapı seti**

```bash
PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q
npm run test:desktop
npm run typecheck --workspace apps/desktop
git diff --check
```

- [ ] **Step 6: Commit**

```bash
git add apps/desktop
git commit -m "feat: show each conflict with its evidence and its cost"
```

---

## Bu planın KAPSAMADIĞI şeyler

Kapsam sınırı bilinçli; her biri nereye ait olduğuyla birlikte:

- **LLM/`LocalExtractor`.** Plan 3. Bu planda tek motor `RuleExtractor`. Spec §6'nın *"LLM açıklar ve önerir"* satırı burada **şablon metne** düşer — spec'in "bozulmadan çalışma" gereği zaten bunu istiyor.
- **Blocking sözlüğü (Bulgu B).** Plan 3, spec §7.
- **Gold set ve eşik kalibrasyonu.** Plan 3, spec §8. `MATCH_THRESHOLD = 0.80` bu plandan **kalibre edilmemiş** çıkar ve öyle işaretlenir.
- **`_read_docx` tablo körlüğü** (STATE.md 0b). Ayrı ve küçük bir düzeltme; bu planın hiçbir task'ı ona dayanmıyor.
- **`planner` kapsam darlığı** (STATE.md madde 5). Metot implementasyonu gerektirir.

---

## Self-Review

**Spec kapsaması (§5-§6):**

| Spec gereği | Task |
|---|---|
| §5 üç ayrı iş: çıkarım / eşleştirme / tür | 5, 6, 7 |
| §5 `MethodologyExtractor` protokolü | 4 |
| §5 `ColumnSummary`'de hücre değeri yok | 4 (testle kilitlendi) |
| §5 sonuç/maruziyet/kovaryat kalıp çıkarımı | 5 |
| §5 bulanık eşleştirme, TR katlama, kısaltma sözlüğü | 6 |
| §5 tür deterministik; belge yalnızca tek yönde düzeltir | 7 |
| §6 çelişkinin bedelini `planner` hesaplar | 8 |
| §6 `confirmed` bayrağının anlamı | 9 |
| §6 toplu kabul, çelişkili ve düşük güvenli hariç | 9 |
| §6 akış kilidi (`dataApproved` çelişki varken false) | 9 (düğme disabled) + mevcut sunucu kapısı |
| §6 ekranlar: ayrı blok, kanıt, rozet düşmesi | 10 |
| §4 Karar B'nin yerine geçen saklama | 1, 2, 3 (STATE.md 0d) |

**Kalan borç, açıkça:** spec §6'nın *"LLM laik dille anlatır"* kısmı Plan 3'e bırakıldı; §7-§8'in tamamı Plan 3.

---

## Execution Handoff

Plan `docs/superpowers/plans/2026-08-24-metodoloji-eslestirme-plan2.md` dosyasında.

İki çalıştırma seçeneği:

1. **Subagent-Driven (önerilen)** — her task için taze bir subagent, task'lar arasında inceleme. Plan 1'de ölçülen ders (STATE.md, kişisel not): dört kusurun dördünü de incelemeler buldu, ikisini yalnızca **final dal incelemesi** yakaladı. Yani task incelemeleri yeterli değil; final dal incelemesi bu planda da zorunlu.
2. **Inline Execution** — bu oturumda, kontrol noktalarıyla.
