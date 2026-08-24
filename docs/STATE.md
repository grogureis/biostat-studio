# STATE.md — biostat-studio

**Son güncelleme:** 2026-08-24 · oturum `biostat-studio-app-8f`
**Dal:** `codex/biostat-studio` · son commit `01ad68a`

> ⚠️ Bu dosya ilk kez 2026-08-24'te oluşturuldu. Öncesindeki geçmiş burada değil;
> `docs/superpowers/plans/`, `docs/validation/` ve git log'a bakın.
> Paralel oturum uyarısı: bu projede aynı anda birden fazla Claude oturumu
> çalışabiliyor. Bu dosyayı güncellerken **kendi bildiğin dilimi** yaz, bilmediğin
> dilimi `bilinmiyor` olarak işaretle — silme.

---

## Tamamlananlar

- Dikey dilim: çalışma özeti → veri alımı → plan → çalıştır → sonuç → Word raporu
  (`docs/superpowers/plans/2026-08-15-biostat-studio-vertical-slice.md`)
- Remediation planı (`docs/superpowers/plans/2026-08-22-biostat-studio-remediation.md`)
- Nonparametrik metotlar + güç/örneklem hesabı
  (`docs/superpowers/plans/2026-08-22-nonparametric-and-power.md`)
- Dış çapraz doğrulama (`docs/validation/2026-08-22-external-cross-validation.md`)
- macOS paketleme (PyInstaller sidecar + Electron), Python 3.12 geçişi
- **2026-08-24:** Metodoloji dokümanından çıkarım — **tasarım tamamlandı ve onaylandı**
  (`docs/superpowers/specs/2026-08-24-metodoloji-cikarimi-design.md`)

## Açık işler

### 1. Metodoloji çıkarımı — implementasyon planı yazılmadı
**Durum:** Tasarım onaylı, `writing-plans` adımına geçilmedi.
**Gerekçe:** Erdem tasarımı bölüm bölüm onayladı (format, çelişki kuralı, toplu kabul,
blocking sözlüğü kapsamı, gold set kaynağı). Sıradaki adım implementasyon planı.
**Ölçüm durumu:** Motor seçimi **ölçülmedi** — gold set henüz kurulmadı.
Ollama kurulu ve ayakta, **yüklü model yok** `[ÖLÇÜM 2026-08-24]`.

### 2. Bulgu A-2 — kodlanmış kategorikler sessizce `continuous`
**Durum:** Ölçüldü, çözülmedi.
`data_intake.py:151` — `numeric_ratio == 1.0` → `continuous`. Ölçüm: `evre`(1-4),
`egitim_duzeyi`(1-5), `merkez_no`(1-8) hepsi `continuous` çıkıyor. Sonucu
`planner.py:427`'de Pearson/Spearman üretilmesi, Welch ANOVA gerekiyorken.
**Gerekçe:** Metodoloji çıkarımı bunu *telafi ediyor* ama *kapatmıyor* — dokümanı
olmayan kullanıcı hâlâ etkilenir. Klinik veride çok sık bir desen.
**Ölçüm durumu:** `[ÖLÇÜM 2026-08-24]` doğrulandı, sentetik seri ile.
**Sahip:** `biostat-studio-app-1b` Task 8'e taşıdı.

### 3. Bulgu B — engelleyici kodlar gösterilmiyor
**Durum:** Ölçüldü. Metodoloji çıkarımı tasarımının Bölüm 4'ü çözüyor.
`PlanReview.tsx:66` — `planner` 20 farklı `blocking_errors` kodu üretiyor, hiçbiri
render edilmiyor. Kullanıcı yalnızca genel bir cümle görüyor.
**Ölçüm durumu:** `[ÖLÇÜM 2026-08-24]` kod sayımı ile doğrulandı.

### 4. Task 8 — remediation / final acceptance gates
**Durum:** Açık; 5 alt maddenin hiçbiri tamamlanmamış.
`[DOKÜMAN: docs/superpowers/plans/2026-08-22-biostat-studio-remediation.md checkbox
durumu — testler koşulmadı]`

1. Tam otomatik gate seti (Python + desktop test, typecheck, prod build,
   `git diff --check`, packaging resource smoke, sidecar self-test, architecture
   checks) — **koşulmadı**.
2. Whole-branch bilimsel/güvenlik review — **yapılmadı**.
3. Operatör (Erdem) gerçek `.xlsx` GUI kabul testi — **tamamlanmadı**.
   Kapsam: import → rol onayı → plan onayı → analiz → iptal → restart/reopen →
   aynı job'dan EN/TR DOCX export.
   **Bu adım en az bir kez importta patlamış, baştan tekrarlanmalı.**
   `[ÖLÇÜM 2026-08-24]` — son commit `01ad68a` gövdesi: sandbox'lı preload ESM
   olarak emit edildiği için `window.biostat` tanımsız kalmış ve IPC'yi geçen
   **her** masaüstü eylemi (workbook import, proje seçimi, rapor dışa aktarımı,
   API çağrıları) reddetmiş; kullanıcıya "The workbook picker could not be
   opened" olarak görünmüş. Düzeltildi (esbuild ile tek parça `preload.cjs`)
   ve smoke test eklendi.
4. DOCX tablo/figür incelemesi + paketli uygulamanın **dışa network bağlantısı
   yapmadığının** doğrulanması — **yapılmadı**.
5. Finishing-branch seçeneklerinin sunumu — sırası gelmedi.

**Madde 3 ile Bulgu A-2 kesişimi:** kodlanmış kategorik içeren gerçek bir workbook
kullanılırsa (klinik veride `evre`/`merkez` çok sık) madde 3'te A-2 ile tekrar
karşılaşılması beklenir.

**Dal durumu** `[ÖLÇÜM 2026-08-24]`: `codex/biostat-studio`,
`origin/codex/biostat-studio`'dan ayrışmış — remote'ta 2, yerelde 1 commit.
Remote'taki ikisi docs-only (`6fab78e` merge, `639e7aa` mimari diyagram), düşük risk.

*(Bu madde gözlemci oturum `biostat-studio-app-1b` tarafından plan dosyası okunarak
raporlandı, `8f` tarafından git ile doğrulanıp yazıldı. 1b Task 8'i uygulamıyor.)*

### 5. `planner` kapsam darlığı
**Durum:** Bilinen sınır, karar verilmedi.
12 metot destekleniyor. Sağkalım, karışık modeller, çoklu maruziyet,
çok düzeyli maruziyet + kovaryat yok. Metodolojik olarak makul çalışmalar
`BlockingPlanError` alıyor.
**Gerekçe:** Genişletme metot implementasyonu gerektirir, LLM çözmez.
Önceki oturumda faz sıralaması konuşulmuş (bkz. AGENTS.md, 2026-08-22 notu).

## Sıradaki iş

**Metodoloji çıkarımı için implementasyon planı yaz** —
`superpowers:writing-plans`, girdi olarak
`docs/superpowers/specs/2026-08-24-metodoloji-cikarimi-design.md`.

Plan yazılmadan önce netleşmesi gerekenler yok; spec kendi kendine yeter.
Planın kapsaması gerekenler, spec §9'daki Faz 1:
doküman alımı · çıkarım arayüzü + 3 motor · eşleştirme · onay katmanı ·
çelişki çözümü · blocking sözlüğü · ölçüm düzeneği.

**Not:** Spec ve bu dosya `efce816` ile commit edildi (2026-08-24). Push edilmedi —
dal `origin/codex/biostat-studio`'dan ayrışmış durumda (remote'ta 2 docs-only commit),
push öncesi önce onların çekilmesi gerekir.
