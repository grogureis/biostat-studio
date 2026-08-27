# Yerel LLM Metodoloji Çıkarımı Plan 3 Implementation Plan

**Durum:** 2026-08-27'de uygulandı, gerçek Word/Excel ve paketli DMG servisiyle doğrulandı.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kurulu Ollama `qwen2.5:14b` modelini metodoloji belgesi ve Excel sütun şemasından güvenli, kanıtlı ve insan-onaylı çalışma/değişken önerileri üretmek için BioStat Studio'ya bağlamak.

**Architecture:** Yerel model yalnızca `127.0.0.1:11434` Ollama API'sine, yapılandırılmış JSON şemasıyla çağrılır. `LocalExtractor` metni kavramlara ve yalnızca yapısal sütun özetlerini gerçek sütun rollerine dönüştürür; `RuleExtractor` her hata durumunda deterministik geri dönüş katmanıdır. LLM çıktısı hiçbir zaman `confirmed=true` yazmaz; planlayıcı kullanıcının Excel ekranında onayladığı gerçek sütun rollerinden beslenir.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, stdlib `urllib`, Ollama `/api/chat`, React 19, TypeScript, Vitest, PyInstaller, Electron Builder.

**Spec:** `docs/superpowers/specs/2026-08-24-metodoloji-cikarimi-design.md`

## Global Constraints

- Hasta verisi ve Excel hücre değerleri modele gitmez; yalnızca metodoloji metni ile `ColumnSummary(name, kind, unique_values, non_missing)` kullanılır.
- Ollama adresi sabit olarak `http://127.0.0.1:11434` kalır; uzak host veya bulut geri dönüşü yoktur.
- Varsayılan model `qwen2.5:14b`; yalnızca yerel model adı `BIOSTAT_LOCAL_LLM_MODEL` ile değiştirilebilir.
- LLM `planner.py`, `analyses.py`, `power.py` veya `reporting.py` karar mantığına girmez.
- Her LLM önerisi `source`, 0..1 `confidence` ve dokümanda doğrulanan `evidence` taşır; kanıt dokümanda bulunamazsa öneri atılır.
- Gold-set kalibrasyonu tamamlanana kadar yerel LLM güveni en fazla `0.79` olur; toplu kabul eşiği `0.80` olduğu için LLM önerileri tek tek insan incelemesinden geçer.
- Ollama/model ulaşılamazsa, zaman aşımı veya geçersiz JSON olursa istek çökmez; `RuleExtractor` çalışır ve UI sınırlı geri dönüşü açıkça gösterir.
- Makine önerileri `confirmed=false`; `confirmed=true` yalnızca kullanıcı eylemiyle yazılır.
- Gerçek `PassiveSurveillance.xlsx` hasta düzeyi veri içerdiği için Git'e veya test fixture'ına kopyalanmaz.

---

### Task 1: Ollama taşıma katmanı ve yapılandırılmış yerel çıkarım

**Files:**
- Create: `services/analysis/biostat_service/extractors/ollama.py`
- Create: `services/analysis/biostat_service/extractors/local.py`
- Test: `services/analysis/tests/test_local_extractor.py`

**Interfaces:**
- Consumes: `MethodologyDocument`, `BriefProposal`, `ColumnSummary`, `RoleProposal`, `select_relevant_text`.
- Produces: `OllamaClient.available(model: str) -> bool`, `OllamaClient.chat(model, messages, schema) -> str`, `LocalExtractor.extract_brief(...)`, `LocalExtractor.match_variables(...)`.

- [ ] **Step 1: RED — taşıma sözleşmesini yaz**

  Sahte `urlopen` ile `/api/tags`'in yalnızca tam model adını kabul ettiğini, `/api/chat` gövdesinde `stream:false`, JSON schema, `temperature:0` ve `keep_alive:"5m"` bulunduğunu; uzak URL kullanılamadığını test et.

- [ ] **Step 2: RED'i doğrula**

  Run: `cd services/analysis && .venv-py312/bin/python -m pytest tests/test_local_extractor.py -v`

  Expected: `ModuleNotFoundError: biostat_service.extractors.ollama`.

- [ ] **Step 3: GREEN — stdlib Ollama istemcisini uygula**

  `OllamaClient` URL'yi sabit sınıf alanından kullanır, durum yoklamasını 2 saniye, çıkarımı 120 saniyeyle sınırlar. HTTP/JSON/timeout hatalarını `LocalExtractionError` sabit kodlarına dönüştürür; ham hata veya yol yayınlamaz.

- [ ] **Step 4: RED — brief şeması, kanıt ve gizlilik testlerini yaz**

  El yapımı JSON yanıtıyla başlık/soru/hipotez/tasarım/sonuç/maruziyet/kovaryat önerilerini doğrula. Dokümanda birebir bulunmayan kanıtın atıldığını, `evidence_offset`'in modelden değil yerel metinden hesaplandığını ve güvenin `0.79` ile sınırlandığını sabitle.

- [ ] **Step 5: GREEN — LocalExtractor brief çıkarımını uygula**

  Pydantic şeması izinli tasarımları ve alanları sınırlar. Sistem prompt'u metnin talimat değil veri olduğunu, bilinmeyeni `null`/`[]` bırakmayı ve kanıtı birebir aktarmayı söyler. Model cevabı `model_validate_json` ile doğrulanır.

- [ ] **Step 6: RED/GREEN — sütun rolü eşleştirmesini uygula**

  Test, prompt'ta hücre değeri bulunmadığını ve yalnızca `name/kind/unique_values/non_missing` bulunduğunu kontrol eder. Modelin uydurduğu sütun, geçersiz rol/tür ve dokümanda bulunmayan kanıt atılır. Aynı sütunda rol ve tür tek `RoleProposal` içinde birleşir.

- [ ] **Step 7: Task 1 testlerini geçir ve commit et**

  Run: `cd services/analysis && .venv-py312/bin/python -m pytest tests/test_local_extractor.py -v`

  Commit: `feat: add evidence-bound local Ollama extractor`

---

### Task 2: Motor seçimi, güvenli geri dönüş ve API entegrasyonu

**Files:**
- Create: `services/analysis/biostat_service/extractors/engine.py`
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `services/analysis/biostat_service/projects.py`
- Test: `services/analysis/tests/test_extractor_engine.py`
- Test: `services/analysis/tests/test_methodology_endpoint.py`

**Interfaces:**
- Consumes: `LocalExtractor`, `RuleExtractor`.
- Produces: `ExtractionRun(brief, engine, fallback_reason)`, `VariableRun(proposals, engine, fallback_reason)` ve API `engine` durum nesnesi.

- [ ] **Step 1: RED — yerel motorun birincil, kural motorunun geri dönüş olduğunu test et**

  Yerel motor tam başarılıysa onun alanları kullanılır; boş alanlar kural motoruyla tamamlanır. Model yok/zaman aşımı/geçersiz yanıtta yalnızca kural sonucu döner ve sabit `fallback_reason` taşır.

- [ ] **Step 2: GREEN — motor orkestratörünü uygula**

  Birleştirme alan bazlıdır; yerel öneri kural önerisini ezer, fakat yerel motorun boş bıraktığı yer kural tabanıyla dolabilir. Kaynak her `Proposal.source` üzerinde korunur.

- [ ] **Step 3: RED — `/v1/methodology/extract` motor durumunu test et**

  Yanıt şu kararlı şekli taşır:

  ```json
  {"engine":{"requested":"local:qwen2.5:14b","used":"local:qwen2.5:14b","fallback_reason":null}}
  ```

  Geri dönüşte `used:"rule"` ve kullanıcıya çevrilebilir sabit neden gelir. Kaynak yolu ve ham Ollama hatası yanıtta yer almaz.

- [ ] **Step 4: GREEN — API'yi orkestratöre bağla**

  `create_app(extractor_factory=...)` test bağımlılığı alır; üretimde varsayılan fabrika `BIOSTAT_LOCAL_LLM_MODEL` veya `qwen2.5:14b` kullanır. `/methodology/extract` ve `/variable-proposals` aynı politikanın iki ayrı çalışmasıdır.

- [ ] **Step 5: Metodoloji kaydına motor adını ekle**

  `MethodologyPayload` ve proje manifesti `extraction_engine` alanını isteğe bağlı taşır; eski projeler alan yokken açılmaya devam eder. Audit olayı model adını taşır, prompt veya model cevabını taşımaz.

- [ ] **Step 6: Task 2 testlerini geçir ve commit et**

  Run: `cd services/analysis && .venv-py312/bin/python -m pytest tests/test_extractor_engine.py tests/test_methodology_endpoint.py tests/test_projects.py -v`

  Commit: `feat: route methodology intake through local AI with safe fallback`

---

### Task 3: Tüm çalışma özeti alanlarını atomik ve görünür öneri olarak doldurma

**Files:**
- Modify: `apps/desktop/src/api/types.ts`
- Modify: `apps/desktop/src/api/client.ts`
- Modify: `apps/desktop/src/features/study/StudyBrief.tsx`
- Test: `apps/desktop/src/features/study/StudyBrief.test.tsx`
- Test: `apps/desktop/src/api/client.test.ts`

**Interfaces:**
- Consumes: API `engine` durumu ve sekiz alanlı `BriefProposalDto`.
- Produces: tek `onChange` ile atomik doldurulmuş `StudyBrief`; her öneride kaynak/kanıt rozeti; yerel AI veya kural geri dönüş durumu.

- [ ] **Step 1: RED — gerçek hedef davranışını test et**

  Bir LLM çıktısının `title`, `question`, `hypothesis`, `design`, `outcome_variables`, `exposure_variables`, `covariates` alanlarını tek seferde doldurduğunu; kullanıcının istek sırasında yaptığı düzenlemeyi ezmediğini test et.

- [ ] **Step 2: GREEN — atomik proposal uygulamasını yaz**

  Sonuç/maruziyet/kovaryat kavramları çalışma özetinde insan tarafından okunabilir geçici kavramlar olarak görünür; Excel onayında gerçek sütun adlarıyla değiştirilir. Aynı async sonuç yedi ayrı stale-state yazımı yapmaz.

- [ ] **Step 3: RED/GREEN — motor durumunu sade dilde göster**

  TR/EN metinler:
  - yerel: `Yerel yapay zekâ önerileri hazırladı; veriler bu Mac'ten çıkmadı.`
  - geri dönüş: `Yerel yapay zekâ kullanılamadı; sınırlı kural tabanlı öneriler gösteriliyor.`

  Ham model/servis hatası kullanıcıya verilmez; Ollama'yı açıp belgeyi yeniden seçme eylemi söylenir.

- [ ] **Step 4: Task 3 testlerini geçir ve commit et**

  Run: `npm test -- --run src/features/study/StudyBrief.test.tsx src/api/client.test.ts`

  Commit: `feat: fill the study brief from reviewed local AI proposals`

---

### Task 4: Excel sütun eşleştirmesi, insan onayı ve doğru hata mesajı

**Files:**
- Modify: `services/analysis/biostat_service/app.py`
- Modify: `apps/desktop/src/api/types.ts`
- Modify: `apps/desktop/src/features/data/DataIntake.tsx`
- Test: `services/analysis/tests/test_methodology_endpoint.py`
- Test: `services/analysis/tests/test_service_security.py`
- Test: `apps/desktop/src/features/data/DataIntake.test.tsx`

**Interfaces:**
- Consumes: `VariableRun`, kullanıcının tam `VariableRole[]` snapshot'ı.
- Produces: onaylanan gerçek sütunlardan yeniden kurulan `StudyBrief` değişken listeleri; aşama bazlı güvenli UI hatası.

- [ ] **Step 1: RED — onaylanan roller brief'i belirlesin**

  Testte metodoloji kavramı `clinical deterioration`, Excel sütunu `kötüleşme_primer` olsun. Kullanıcı sütunu `outcome` olarak onaylayınca kalıcı `StudyBrief.outcome_variables == ["kötüleşme_primer"]` olmalı; kavram adı planlayıcıya gitmemeli.

- [ ] **Step 2: GREEN — `_brief_from_confirmed_roles` uygula**

  Tam/benzersiz/izinli/onaylı rol snapshot'ı önce doğrulanır. En az bir `outcome` zorunludur. `outcome`, `exposure`, `covariate` ve en fazla bir `pair_id` alfabetik ve deterministik sırada brief'e yazılır; başlık/soru/hipotez/tasarım değişmez. Sonra audit ve persist yapılır.

- [ ] **Step 3: RED/GREEN — LLM sütun önerilerini UI'da göster**

  Rol/tür önerileri `confirmed=false` başlar, kanıtıyla görünür. Kalibre edilmemiş `0.79` LLM önerisi toplu kabul edilmez; kullanıcı tek tek seçince onaylanır.

- [ ] **Step 4: RED — Excel hata aşamalarını ayır**

  Ayrı testler: picker reddi → picker mesajı; profil 422 → workbook okuma mesajı; proje/brief 422 → çalışma özeti eksik mesajı; değişken önerisi hatası → eşleştirme mesajı. Hiçbiri dosya yolu veya backend ayrıntısı göstermez.

- [ ] **Step 5: GREEN — `DataIntake` hata durum makinesini uygula**

  Tek `pickerFailed` boolean yerine `picker|profile|brief|matching|null` kullan. Kullanıcıya hangi alanı düzelteceğini söyle; yeni dosya seçimi hatayı temizler.

- [ ] **Step 6: Task 4 testlerini geçir ve commit et**

  Run: `cd services/analysis && .venv-py312/bin/python -m pytest tests/test_methodology_endpoint.py tests/test_service_security.py -v`

  Run: `npm test -- --run src/features/data/DataIntake.test.tsx`

  Commit: `fix: reconcile document concepts with confirmed workbook columns`

---

### Task 5: Gerçek dosya kabulü, tüm kapılar ve paketleme

**Files:**
- Create: `services/analysis/scripts/accept-methodology.py`
- Modify: `README.md`
- Modify: `docs/STATE.md`
- Test: `services/analysis/tests/test_accept_methodology_script.py`

**Interfaces:**
- Consumes: kullanıcının yerel Word/Excel yolları; veri hücrelerini yazdırmayan servis API'si.
- Produces: motor, önerilen brief alanları, sütun rol eşleştirmeleri ve eksik/engelli yetenekleri içeren değersiz kabul özeti.

- [ ] **Step 1: RED/GREEN — gizlilik korumalı kabul koşucusunu yaz**

  Koşucu dosya yolunu, hücre değerini veya kanıt metnini stdout'a yazmaz. Yalnızca dosya adı, satır/sütun sayısı, motor, öneri alanları ve eşleşen sütun adlarını JSON verir. Test sentetik dosyalarla çalışır.

- [ ] **Step 2: Gerçek `Methods_Section.docx` ile yerel model kabulünü çalıştır**

  Beklenen kapılar: `engine.used == "local:qwen2.5:14b"`; title/question/hypothesis/design/outcome dolu; evidence alanları dokümanda doğrulanmış; ham metin loglanmamış.

- [ ] **Step 3: Gerçek `PassiveSurveillance.xlsx` ile yapısal eşleştirmeyi çalıştır**

  Beklenen kapılar: 500 satır/54 sütun; en az bir gerçek outcome ve exposure sütunu; LLM girdisinde hücre değeri yok; desteklenmeyen Firth/Little/MI istekleri yapılabilir gibi sunulmuyor.

- [ ] **Step 4: Tüm otomatik kapıları taze çalıştır**

  Run: `cd services/analysis && MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/biostat-local-llm .venv-py312/bin/python -m pytest -v`

  Run: `npm test -- --run`

  Run: `npm run typecheck --workspace apps/desktop`

  Run: `npm run build --workspace apps/desktop`

  Run: `git diff --check`

- [ ] **Step 5: Arm64 uygulama ve DMG üret, paketli kabul kapılarını çalıştır**

  Mevcut yayın script'iyle sidecar ve Electron paketini üret. DMG bütünlüğü, derin ad-hoc imza, arm64 mimari, sidecar self-test ve DMG içinden uygulama başlatma kontrol edilir. Ollama açıkken paketli metodoloji çıkarımı yerel motoru kullanmalı; kapalıyken UI kural geri dönüşünü açıkça göstermeli.

- [ ] **Step 6: Dokümantasyon, ErdemOS, birleştirme ve yayın**

  README ve `docs/STATE.md` gerçek kapı sayıları/model davranışıyla güncellenir. `codex/local-llm-intake` temiz kapıdan sonra `codex/biostat-studio` ile birleştirilir, `origin/codex/biostat-studio` gönderilir, ErdemOS `## Nerede kaldım`/`## Kararlar` güncellenir ve `project_sync.py --quiet` çalıştırılır.

  Commit: `release: integrate local methodology AI and publish macOS package`
