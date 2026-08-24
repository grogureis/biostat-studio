# STATE.md — biostat-studio

**Son güncelleme:** 2026-08-24 · oturum `biostat-studio-app-8c`
**Dal:** `feat/methodology-intake` · son commit `472cb2c` · ayrım noktasından beri **19 commit**
(`codex/biostat-studio` @ `28af9c9`'dan dallandı; birleştirilmeyi bekliyor)

**Devralma doğrulaması `[ÖLÇÜM 2026-08-24, oturum 8c]`** — devir notundaki iddialar tek tek koşuldu:
- `PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python -m pytest services/analysis/tests -q`
  → **280 passed**. `npm run test:python` hâlâ bozuk (venv editable kablolaması), kök neden `doğrulanmadı`.
- `npm run test:desktop` → **67 passed** (9 dosya).
- Typecheck: kökte `typecheck` script'i **yok**; `apps/desktop`'ta var
  (`cd apps/desktop && npx tsc --noEmit`) → **temiz**. Devir notundaki "npm run typecheck" yanıltıcı.
- Çalışma ağacı temiz.
- **Merge kuru testi:** `git merge-tree --write-tree codex/biostat-studio feat/methodology-intake`
  → **exit 0, çakışma yok** (STATE.md dosyası dahil). STATE.md'nin çakışma uyarısı ölçümle düştü.
- **Ayrışma:** `origin/codex/biostat-studio` 2 commit ileri (docs-only `6fab78e`, `639e7aa`),
  yerel `codex/biostat-studio` **3** commit ileri. (Bu dosya daha önce "1" diyordu — bayattı.)

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

- **2026-08-24:** Metodoloji doküman alımı — **Faz 1 / Plan 1 kodlandı ve incelendi**
  (`docs/superpowers/plans/2026-08-24-metodoloji-dokuman-alimi.md`, 8 task, 15 commit,
  dal `feat/methodology-intake`). 277 Python + 67 desktop = **344 test**, typecheck temiz.
  Final dal incelemesi (opus) "ready to merge" verdi. **Henüz birleştirilmedi.**
  Kullanıcı bir metodoloji dokümanı (docx/pdf/txt/md) yükler → metin çıkarılır → yöntem
  bölümlerine daraltılır → kural motoru çalışma tasarımını **kanıt cümlesiyle birlikte** önerir
  → kullanıcı onaylar. `planner.py` ve analiz katmanı **hiç değişmedi**.

## Açık işler

### 0. Metodoloji çıkarımı Plan 1 — birleştirme kararı bekliyor
**Durum:** Kod hazır, inceleme temiz, **merge/push kararı verilmedi**.
`feat/methodology-intake` dalı `codex/biostat-studio`'dan `28af9c9` ile ayrıldı.
**Dikkat:** `codex/biostat-studio` kendisi `origin`'den ayrışmış (remote'ta 2 docs-only commit).
Bu dosya iki dalda da mevcut — birleştirmede çakışabilir.

**Bu planın ölçülmüş ve düzeltilmiş kusurları** (hepsi inceleme sırasında bulundu, hiçbiri
testler yeşilken görünmüyordu):
- İstisna zinciri (`from exc`) dosya yolunu `traceback.format_exception()` çıktısına sızdırıyordu
- `pypdf` PyInstaller spec'inde yoktu + import tembeldi → **paketlenmiş uygulamada PDF çökerdi**
- Türkçe `İ`, `.lower()` ile iki kod noktasına açılıyor → bölüm başlıkları kaçıyor **ve** dilim
  konumları kayıyordu
- O düzeltme İngilizce ALL-CAPS başlıkları kırdı (iki katlama birleşimiyle çözüldü)
- `evidence` alanı noktalama içermeyen bir dokümanın **tamamını** yanıta döndürüyordu
- Kural motoru "retrospective cohort + longitudinal follow-up" ifadesini **`repeated`** sayıyordu
  ve gösterdiği kanıt cümlesi kendi cevabını çürütüyordu
- React bayat closure: çıkarım sürerken yazılan klinik metin sessizce geri alınıyordu

### 0b. Plan 1'den taşınan bilinen borçlar (Plan 2 öncesi)
- **Spec §4 Karar B düşürüldü, gerekçesi dayanaksız kaldı.** `methodology_documents` oturum
  saklaması bilinçli olarak eklenmedi (evict edilmeyen, hiç okunmayan, yükleme başına 200k
  karakter tutan ölü durum + gizlilik yüzeyi). Final inceleme düşürmeyi **doğru** buldu. **Ama**
  spec'in "bir kez oku, oturumda tut" gerekçesi capability jetonunun tek kullanımlık olmasına
  dayanıyordu: jeton tüketiliyor, dosya saklanmıyor, **Plan 2'nin metne geri dönüş yolu yok.**
  Plan 2 saklamayı kendi ihtiyacıyla birlikte kurmak zorunda — yanlış öncülden başlamayın.
- `contracts.py` — kırpılmış kanıt `…` ile bittiği için `evidence_offset` `None` oluyor.
  Çözümü tek satır (`find(evidence.rstrip("…"))`); kanıt vurgulaması gerekirse lazım.
- `EVIDENCE_MAX_CHARS` iki farklı sınır anlamına geliyor: pencere ±400 (iç değer ~801'e çıkabilir),
  serileştirme tavanı 401. Gizlilik garantisi serileştiricide, ama isim yanıltıcı.
- `.proposal-badge`, `design` doğruyken `evidence` null olsa da render ediliyor. Bugün ulaşılamaz;
  **Plan 2'nin `LocalExtractor`'ı kanıtsız tasarım döndürebilir.**
- `StudyBrief.tsx:120` sunucudan gelen `string`'i `StudyDesign`'a runtime kontrolü olmadan
  cast ediyor. İkinci bir motor geldiğinde sözlük dışı bir değer doğrudan `brief`'e girer.
- Spec §6'nın "kullanıcı alanı elle düzenlerse `dokümandan` işareti düşer" kuralı **Plan 2 kapsamı**;
  bugün rozet elle değiştirilen alanda da duruyor.
- `_read_docx` yalnızca `document.paragraphs` okuyor — docx **tabloları atlanıyor**. Tamamen
  tablodan oluşan bir docx `no_extractable_text` verir ve UI "taranmış PDF'i metne çevirin"
  metnini gösterir; Word dosyası için yanlış yönlendirme.
- Electron IPC handler **gövdelerinin** doğrudan testi yok (dört picker'ın hepsinde).
  Sonucu iki katmanda kapsanıyor (`path-capabilities.test.ts`, `api-proxy.test.ts`).
- `methodology_intake.py` FIX 5 sonrası: metin boş **ve** hash okunamıyorsa hata kodu
  `no_extractable_text` yerine `unreadable_document` oluyor. Güvenli, testsiz, TOCTOU-nadir.

### 0d. Plan 2'yi bloke eden tek mimari karar — **Erdem'in kararı, verilmedi**
`[ÖLÇÜM 2026-08-24, oturum 8c — kod okundu]`

Madde 0b "Plan 2 doküman metnine dönüş yolunu kendisi kurmak zorunda" diyordu. O yolun
üç seçeneği var ve seçim Plan 2'nin görev sırasını belirliyor, dolayısıyla plan yazılmadan
önce verilmeli. Ölçülen kısıtlar:

- `client.ts:190` — `methodologyCapability = null` **gönderimden önce** çalışıyor. Token
  tek kullanımlık; başarısız istek bile token'ı öldürüyor (kodun kendi yorumu bunu söylüyor).
- `app.py:70` `MethodologyExtractRequest` yalnızca `source_path` taşıyor. Extract, `study`
  adımında, **proje daha yaratılmadan** çağrılıyor → sunucuda saklamanın asılacağı bir
  `ProjectContext` yok. Global bir sözlük demek: TTL/evict gerektiren proje-dışı durum.
  0b'deki ret gerekçesi bu ölçümle **hâlâ geçerli**.
- `StudyBrief.tsx:117` — `extraction` bileşenin **yerel** state'inde; App'e hiç çıkmıyor,
  dolayısıyla `DataIntake` onu göremiyor. Eşleştirme adımına taşınması için bir yol gerek.

**Yollar:**
(a) **Sunucuda sakla** (spec §4 Karar B'nin özgün hali) — proje-dışı global durum + evict.
(b) **İkinci capability token** (Excel deseni, `main.ts:69-70`) — dosya ikinci kez okunur;
    araya kullanıcı adımı girdiği için hash değişmiş olabilir, yeni bir hata yolu doğar.
(c) **Seçilmiş metni yanıtta döndür**, renderer taşısın, eşleştirmede geri göndersin —
    `select_relevant_text` zaten 12.000 karaktere kırpıyor (`rule.py:19 SELECTION_BUDGET`).
    Sunucu durumsuz kalır, yeni token yok, dosya ikinci kez okunmaz.

**8c'nin tavsiyesi: (c).** Gerekçe: üçü arasında **yeni durum yaratmayan tek yol**. Metin
zaten `evidence` alanlarıyla parça parça renderer'a iniyor; gizlilik sınırı hasta verisinde
ve o sınır `ColumnSummary`'de hücre değeri olmamasıyla korunuyor — metodoloji metni o
sınırın içinde değil. **Karar verilmedi.**

### 0e. Plan 2'nin işini kolaylaştıran iki hazır altyapı `[ÖLÇÜM 2026-08-24, oturum 8c]`
Plan 2 sıfırdan kurmayacak; ikisi de çalışır durumda:
- `app.py:386 _validated_roles` **zaten** `not role.confirmed` görünce 422
  `unconfirmed_variable_roles` atıyor. **Sunucu kapısı var.** Bulgu A-1 bir sözleşme açığı
  değil, yalnızca `DataIntake.tsx:81`'in her rolü `confirmed: true` damgalamasıyla UI'da
  atlanan bir kapı. Düzeltme tek katmanda.
- `app.py:427 _apply_approved_kinds` onaylanan `kind`'ı okunan frame'e gerçekten uyguluyor
  (`continuous` → `to_numeric`, `binary`/`categorical` → `string`). Bulgu A-2'yi kapatmak
  için **yeni dönüşüm kodu gerekmiyor**; eksik olan doküman düzeltmesi ve insan kapısı.

### 0c. Yerel LLM — ÖN ÖLÇÜM YAPILDI (2026-08-24), Plan 3 kararı bekliyor
**Durum:** Ollama'da model yoktu, hiçbir şey ölçülmemişti. Artık ölçüldü.
Ölçüm düzeneği depoda: `scripts/eval/` (`gold_set.json`, `run_eval.py`, `--fetch`).
Korpus metinleri **commit edilmedi** (PMC açık erişim yeniden dağıtımı belirsiz); kimlikler,
altın etiketler ve çekme betiği commit edildi.

**Kurulu modeller:** `qwen2.5:14b` (9.0 GB), `qwen2.5:7b` (~4.7 GB). Ollama ayakta.
**Erdem'in tercihi:** *"daha iyi model sistemde olsun"* → varsayılan **14b**.
Ölçüm bunu çürütmüyor, yalnızca "7b de yeterdi" diyor — ayırt edici fark yok, seçim tercihte kalıyor.
**Tavan:** 24 GB RAM. `32b` Q4 ~20 GB; Electron + Python + pandas ile aynı anda çok dar. `doğrulanmadı`

**ÖLÇÜLEN — dört bulgu:**
1. **Yerel rota uygulanabilir.** Tasarım sınıflandırmasında 7b ve 14b doğru ve hızlı
   (model yüklendikten sonra saniye altı).
2. **Ama bu görev üç motoru AYIRT ETMİYOR.** Kural motoru, 7b ve 14b aynı skoru alıyor.
   **Kararı verecek görev bu değil** — asıl ayırt edici, kural motorunun neredeyse hiç
   yapamadığı **kavram çıkarımı** (sonuç/maruziyet/kovaryat). O **hiç ölçülmedi.**
3. **Kural motorunun iki gerçek kusuru** yalnızca gerçek dergi metnine karşı koşulduğu için
   bulundu (uydurma cümlelerle görünmüyordu): dergiler `case–control`'ü **en dash** ile yazıyor,
   desen kaçırıyordu; ve 2500 karakter sonra geçen bir **alıntı**, makalenin kendi tasarım
   beyanını yeniyordu. İkisi de `042a322` ile düzeltildi (280 test).
4. **Türkçe sözlük eksik:** `"rastgele ... ayrıldı"` Türkçe'de randomizasyonun standart
   ifadesi ve hiçbir desen eşleşmiyor. **Düzeltilmedi.**

**AÇIK ÜRÜN SORUSU — cevaplanmadı, Erdem'in kararı:**
Gerçek Türkçe Methods bölümlerinin **yarısı tasarımını hiç adlandırmıyor** ("Bu retrospektif,
tek merkezli, gözlemsel çalışma..."). Doğru cevap nedir?
(a) `cohort` — epidemiyolojik konvansiyon: ardışık hastaların sonuç için izlenmesi retrospektif
kohorttur. (b) `None` — spec'in "emin olmadığı yeri boş bırakır, uydurmaz" kuralı.
Bu karar gold set'in ne ölçtüğünü belirler; verilmeden gerçek set kurulamaz.

**KRİTİK UYARI — ölçümü geçersiz kılan tuzak:**
Aynı PMC kimlikleri, iki farklı "Methods bölümünü çıkar" kuralıyla **farklı skorlar** veriyor
(ilk probe "ilk >400 karakter" → 9/9; depodaki koşucu "en uzun bölüm" → 7/9). Spec §5 bunu
bölüm bulucu için uyarmıştı; aynı tuzak **korpus kurucu** için de geçerli ve ona düştük.
**Gerçek gold set kurulmadan önce korpus çıkarma kuralı sabitlenmeli**; değiştiği anda eski
sayıların hepsi geçersizdir. İki mevcut ölçüm **karşılaştırılamaz.**

**Sıradaki ölçüm (Plan 3'ün ilk işi):** kavram çıkarımı — sonuç/maruziyet/kovaryat.
Aday korpus zaten seçildi ve nitelik kapısından geçti (>2500 karakter, eksiksiz Methods),
`gold_set.json` → `sonraki_korpus_adaylari`. **Etiketlenmedi.** İçinde 3 adet `repeated`
örneği var — mevcut sette hiç yoktu.

### 1. Metodoloji çıkarımı — Plan 2 ve Plan 3 yazılmadı
**Plan 2 — Değişken eşleştirme ve çelişki çözümü:** `match_variables`, bulanık sütun eşleştirme,
çelişki tespiti, `planner.build_plan`'ın iki kez çağrılıp bedelin hesaplanması, `DataIntake.tsx`
onay bloğu, `confirmed` bayrağının düzeltilmesi (Bulgu A-1). Spec §5-§6.
**Plan 3 — Blocking sözlüğü ve ölçüm:** 20 kodluk TR/EN sözlük, `PlanReview.tsx` render'ı,
PubMed gold set (30-50 eleme + 15 kasıtlı kabul seti), `scripts/eval-extractors.py`,
`LocalExtractor` (Ollama). Spec §7-§8.
**Durum:** İkisi de yazılmadı. Spec ikisini de kapsıyor.

### 1b. (eski madde) Metodoloji çıkarımı — implementasyon planı yazılmadı
**Durum:** ARTIK GEÇERLİ DEĞİL — Plan 1 yazıldı ve kodlandı (bkz. madde 0).
**Gerekçe (tarihsel):** Erdem tasarımı bölüm bölüm onayladı (format, çelişki kuralı, toplu kabul,
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
**⚠️ Plan 1 bunun maliyetini ARTIRDI — final incelemenin tespiti:** Bu daldan önce
`brief.design`, `build_plan`'a giden girdiler arasında insanın *zorunlu olarak* seçtiği
sonuncusuydu (varsayılanı `cross_sectional` olan bir açılır liste). Plan 1 onu otomatik
dolduruyor. `DataIntake.tsx:81` hâlâ her rolü `confirmed: true` damgaladığı için (Bulgu A-1),
dokümanı yükleyip tıklayarak ilerleyen bir kullanıcı artık `build_plan`'a **hem çalışma
tasarımı hem her değişken türü makine seçimiyle** ve ikisinde de açık bir insan kapısı olmadan
varıyor. Spec §6 otomatik doldurmayı onaylıyor, dolayısıyla ihlal değil — ama **A-1 ve A-2'yi
kapatan Plan 2'nin gecikmesi artık daha pahalı.**

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

**1. `feat/methodology-intake` dalının birleştirme kararı — Erdem'in kararı, verilmedi.**
Kod hazır, inceleme temiz (344 test, typecheck temiz, çalışma ağacı temiz).
Sıralama önerisi: **önce Task 8'in operatör kabul testi** (madde 4) koşulsun, sonra bu dal
birleşsin. Gerekçe: kabul testi gerçek bir `.xlsx` ile uçtan uca akışı sınıyor; bu dal o akışın
girişine yeni bir adım ekliyor. Kabul testi zaten bir kez importta patlamıştı (`01ad68a`).

**2. Plan 2'yi yaz** (`superpowers:writing-plans`, girdi spec §5-§6):
değişken eşleştirme + çelişki çözümü + `confirmed` bayrağının düzeltilmesi.
**Başlamadan önce madde 0b'yi okuyun** — özellikle spec §4 Karar B'nin dayanaksız kalmış
gerekçesini; Plan 2 doküman metnine geri dönüş yolunu kendisi kurmak zorunda.
**BLOKE:** madde **0d** — metne dönüş yolu (a/b/c) seçilmeden plan yazılmaya başlanmadı;
görev sırası bu seçime bağlı. 8c'nin tavsiyesi (c). Ayrıca madde **0e**: `_validated_roles`
ve `_apply_approved_kinds` hazır, Plan 2 onların üstüne kurulmalı — yeniden yazmamalı.

**3. Plan 3'ü yaz** (spec §7-§8): blocking sözlüğü + gold set + ölçüm + `LocalExtractor`.
Motor seçimi **ölçümsüz yapılmayacak**. Ollama kurulu ve ayakta, **yüklü model yok**
`[ÖLÇÜM 2026-08-24]`.

**Push durumu:** Hiçbir şey push edilmedi. `codex/biostat-studio` `origin`'den ayrışmış
(remote'ta 2 docs-only commit: `6fab78e`, `639e7aa`); push öncesi çekilmeli.
