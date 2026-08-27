# STATE.md — biostat-studio

**Son güncelleme:** 2026-08-27 · Codex App
**Aktif geliştirme:** `.worktrees/biostat-studio` · `codex/biostat-studio`

### Metodoloji akışı ana geliştirme dalına alındı — 2026-08-27

`origin/codex/biostat-studio` üzerindeki iki dokümantasyon commit'i önce yerel dala
`544204c` ile alındı; tamamlanmış `feat/methodology-matching` dalı ardından `09a64eb`
ile çakışmasız birleştirildi. Birleştirilmiş kaynakta taze tam kapı ölçümü:
Python **327 geçti + 1 ortam koşullu skip**, desktop **76/76**, TypeScript typecheck,
üretim derlemesi ve `git diff --check` temiz.

İki dilli README anlatısı metodoloji belgesi alımı, kalıcı yerel metin, muhafazakâr
değişken eşleştirme, gerçek planner etkili çelişki çözümü ve insan onayı sınırıyla
güncellendi. Paketleme de gerçekte ad-hoc imza kullanacak ve iCloud File Provider'ın
FinderInfo özniteliklerinden etkilenmemek için imza/DMG üretimini `/private/tmp` altında
yapacak biçimde düzeltildi. Yeni arm64 DMG; paketli preload/renderer smoke, gömülü servis
öz testi, katı kod imzası ve `hdiutil verify` kapılarından geçti.

Teslim dosyası: `release/BioStat Studio-0.1.0-arm64.dmg` (189 MB), SHA-256
`3e310e57aafc5ee9511406a60a394a002d4c2bb2b24c19a5cbd8f8c98bda1d4b`.
Apple Developer ID/notarization yoktur; Gatekeeper uyarısı beklenir. Paketli uygulamada
gerçek araştırma Excel'iyle GUI operatör kabul testi hâlâ ayrı ve açık ürün kapısıdır.

### Plan 2 tamamlandı — 2026-08-27

Metodoloji eşleştirme planının 10/10 görevi tamamlandı. Task 10 commit'i `c6ec726`:
çelişkili değişkenler listenin üstünde kanıt ve gerçek planner maliyetiyle
gösteriliyor; metot kimlikleri ortak EN/TR etiket yardımcısından geçiyor; insan
veri/doküman sınıflandırmasını açıkça seçiyor. Dokümandan gelen tasarım rozeti ve
kanıtı, kullanıcı alanı düzenlediğinde düşüyor.

RED ölçümü 19/21 geçer ve iki beklenen kırık; GREEN/tam kapı ölçümü Python
327 geçti + 1 skip, desktop 76/76, typecheck ve diff kontrolü temiz. Final dal taraması
bir mevcut terminal-durum/audit yarışı yakaladı: istemci `cancelled` durumunu kalıcı
audit callback'i bitmeden görebiliyordu. Deterministik RED testle doğrulandı ve `92e8a52`
ile terminal durum callback sonrasına alındı; yeni açık Critical/Important bulgu yok.
Plan 3'e devredilen iki ölçülmüş sınır açık:
kalibre edilmemiş/dar kavram-sütun eşleştirme ve Türkçe fiil-sonu kovaryat cümlelerinde
kural motorunun bilinçli sessizliği. Paketli uygulamada gerçek Excel ile GUI operatör kabul
testi de ayrı bir ürün kapısı olarak açık.

---

### Önceki birleştirme kaydı — 2026-08-24

### BİRLEŞTİRME YAPILDI — 2026-08-24, Erdem'in kararı
22 commit `codex/biostat-studio`'ya girdi. **Push edilmedi.** `origin` hâlâ 2 docs-only commit
ileride (`6fab78e`, `639e7aa`); push öncesi çekilmeli.

**Açıkça kaydediliyor:** madde 4/3'teki **operatör GUI kabul testi koşulmadan** birleştirildi.
8c'nin tavsiyesi "önce kabul testi" idi; Erdem birleştirmeyi seçti, tavsiye tekrarlanmayacak.
**Kabul testi hâlâ açık bir iş** ve şimdi merge edilmiş kod üzerinde koşulacak.

**Merge sonrası kapı seti `[ÖLÇÜM 2026-08-24]`:** 280 Python + 67 desktop passed, `tsc --noEmit`
temiz, çalışma ağacı temiz, merge çakışmasız.

### ⚠️ venv arızası — ÖLÇÜLDÜ, kısmen çözüldü, kök nedeni açık
Devir notu *"1b'nin worktree'sindeki venv sağlam"* diyordu. **Değilmiş.** İki ayrı arıza var:

1. **`.worktrees/biostat-studio` venv'i `biostat_service`'i site-packages'a KOPYA olarak
   kurmuştu** (editable değil). `npm run test:python` kaynak ağacı değil, venv içindeki
   **eski kopyayı** test ediyordu — yani yeşil sonuçlar yanlış kodu ölçüyordu. Bu, import
   hatası veren arızadan **daha tehlikeli**: sessizce geçiyor. Kopya kaldırıldı,
   `pip install -e services/analysis --no-deps` yapıldı.
2. **Editable kurulum da startup'ta devreye girmiyor** — her iki worktree'de de. Ölçülenler:
   `.pth` dosyası yerinde ve içeriği doğru (`import ...finder; ...install()`, BOM yok);
   finder modülü bulunabiliyor; **elle `exec(line)` çalıştırıldığında import çalışıyor**;
   ama `site` startup'ta bunu uygulamıyor ve hata da yazmıyor. `sys.flags.no_site=0`,
   `pyvenv.cfg` normal, venv algılanıyor. **Kök neden `doğrulanmadı`** — arama burada
   bilinçli olarak kesildi, çözüm kablolamadan bağımsız yapıldı.

**Kalıcı çözüm (uygulandı):** `package.json` → `test:python` script'i artık
`PYTHONPATH=services/analysis` ile başlıyor. `scripts/test-all.sh` bu script'i çağırdığı için
tam kapı seti de düzeldi. `[ÖLÇÜM: npm run test:python → 280 passed]`

**Yeni bağımlılık uyarısı:** merge `pypdf==5.9.0` getirdi ve mevcut venv'lerde yoktu. Yeni bir
worktree açan ya da merge çeken herkes **`pip install -r services/analysis/requirements.lock`
koşmalı** — sürüm kayması istatistik sonuçlarını sessizce değiştiriyor (önceki oturumda ölçüldü).

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

**8c'nin ilk tavsiyesi (c) idi ve YANLIŞ ÖNCÜLE dayanıyordu.** Öncül: "metin yalnızca Excel
eşleştirmesi sırasında lazım, o hâlde taşınması yeter." Erdem bunu düzeltti (2026-08-24):

> *"metodoloji — çalışmanın PICO'su için de gerekli, istatistiksel planlama için de gerekli.
> Sadece Excel'i aldığımızda gerekli olarak ifade edersek yanılırız. Kullanıcı uygulamaya
> belge yükleyecek, orada onu muhafaza etmeli."*

Belge geçici bir girdi değil, **çalışmanın kalıcı parçası**. Taşıma değil, ev gerekiyor.

---

#### KARAR — 8c, Erdem'in devrettiği yetkiyle (*"en randımanlı nerede ise öyle saklasın, sen belirle"*)

**Çıkarılan metin proje klasöründe yaşar. Orijinal belge kopyalanmaz. Renderer yalnızca
proje doğana kadar köprüdür.**

Kararı belirleyen ölçüm — **desen zaten var:** `projects.py:508` Excel'i projeye
**kopyalıyor** (`source/source.xlsx`, `test_projects.py:75` doğruluyor). Yani `.biostat`
klasörü hâlihazırda kendi kendine yeten bir kayıt; belgeyi oraya koymak yeni bir kavram
değil, var olanı genişletmek.
*(Yan bulgu: `create_project` docstring'i "without copying its source dataset" diyor —
**yanlış**, kopyalıyor. Düzeltilmeli.)*

**Neden metin, orijinal dosya değil:**
- Belgeden çıkarılabilecek tek şey metindi ve çıkarıldı; `.docx`/`.pdf` bir daha okunmayacak.
- Metin ≤200.000 karakter ≈ 200 KB. Excel farklı: veri tekrar tekrar okunuyor, hash'i
  doğrulanıyor, satır satır analiz ediliyor — orada dosyanın kendisi gerekli.
- Denetim için dosya adı + `sha256` + format saklanır; "hangi belgeden geldi" cevaplanır.

**Ham metin saklanır, kırpılmış seçim DEĞİL.** `select_relevant_text` her okumada yeniden
hesaplanır. Gerekçe madde 0c'nin ölçülmüş tuzağı: çıkarma kuralı değişince eski sayılar
geçersizleşiyor. Ham metin duruyorsa kural değişse de eski projeler yeni kuralla okunur.

**Akış:**
1. `/v1/methodology/extract` yanıtına tam `text` + `source_name` eklenir.
2. Renderer bunu tutar — ama `StudyBrief.tsx`'in yerel state'inde değil, **App/store
   seviyesinde** (bugün yerel; `StudyBrief.tsx:117`).
3. `POST /v1/projects` isteğine `methodology` bloğu eklenir → `create_project` onu
   `source/methodology.txt` + manifest `methodology: {sha256, format, char_count,
   truncated, original_name}` olarak yazar.
4. Proje zaten açıkken belge yüklenirse `POST /v1/projects/{id}/methodology` aynı yere
   yazar; `AUDIT_EVENT_TYPES`'a `methodology_document_attached` eklenir.
5. Sonraki her tüketici — PICO doldurma, değişken eşleştirme, çelişki açıklaması, LLM
   planlama — metni **projeden** okur. Renderer bir daha taşımaz.

**Kabul edilen sınır, gizlenmiyor:** proje yaratılmadan (yani Excel verilmeden) uygulama
kapanırsa metin kaybolur, belge yeniden yüklenir. Bu pencereyi kapatmak proje-öncesi
kalıcı taslak deposu demek (TTL + temizlik + çakışma) — 0d'de reddedilen (a)'nın ta kendisi.
Faydası birkaç saniyelik tekrar yükleme; bedeli evict edilmeyen durum. **Ölçülmedi**,
kullanıcı bu pencerede sık kapatıyorsa karar yeniden açılmalı.

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

### 1. Metodoloji çıkarımı — **Plan 2 YAZILDI**, Plan 3 yazılmadı
**Plan 2:** `docs/superpowers/plans/2026-08-24-metodoloji-eslestirme-plan2.md`
(2026-08-24, oturum 8c · **10 task**, 1611 satır · kodlanmadı, yalnızca yazıldı).
Kapsam: belgenin projede kalıcılaşması (0d kararı) → kavram çıkarımı → bulanık eşleştirme →
çelişki tespiti → çelişkinin `planner` ile fiyatlanması → `confirmed` düzeltmesi → onay ekranı.
LLM **yok** (Plan 3); tek motor `RuleExtractor`. `planner.py` yine değişmiyor.

**Plan yazılırken ölçülen iki kusur** (ikisi de plan taslağındaydı, kod yazılmadan bulundu):
1. **Planın kendi boşluğu:** ilk taslakta kavram çıkarımı task'ı yoktu. `rule.py:85-91`
   `extract_brief` yalnızca `design` dolduruyor — `outcome/exposure/covariate_concepts` boş
   tuple dönüyor. Eşleştirme task'ı boş listeyi eşleştirecekti ve **testleri yeşil geçecekti**
   ("hiç öneri yok" geçerli bir çıktı). Task 5 olarak eklendi, sonraki tasklar kaydırıldı.
2. `app.py:28` `MethodologyDocument` ve `MAX_DOCUMENT_CHARS`'ı **import etmiyor**; Task 2 ve 8
   ikisini de kullanıyor. Plana açık import adımı yazıldı.

**Kalibre edilmemiş sabit:** `MATCH_THRESHOLD = 0.80` (`extractors/matching.py`). `doğrulanmadı`.
Yanlış olmasının bedeli bilinçli olarak asimetrik: eşiğin altındaki eşleşmeler toplu kabulün
dışında kalıp kullanıcıya tek tek sorulur → yüksek eşik *daha çok soru*, düşük eşik *sessiz
yanlış rol*. Yükseğe eğildi. Plan 3 gold set'inden sonra güncellenmeli.

### 1a. (eski madde) Plan 2 ve Plan 3 yazılmadı
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

**⏸️ Codex App'e devir teslim — 2026-08-27.** Plan 2 çalıştırması **9/10 task**.
Task 9 `4565c4e` ile commitli; Task 10 test-first RED noktasında duruyor.

**Dönüşte ilk iş — Task 10 GREEN:** çalışma ağacında yalnızca iki test dosyası değişik:
`apps/desktop/src/features/data/DataIntake.test.tsx` ve
`apps/desktop/src/features/study/StudyBrief.test.tsx`. Yeni iki test beklenen nedenle kırık:
conflict paneli henüz render edilmiyor; kullanıcı önerilmiş tasarımı değiştirince doküman rozeti
henüz düşmüyor. Hedefli sonuç **21 test: 19 geçti, 2 RED**. Üretim koduna Task 10 için henüz
dokunulmadı.

Uygulama sırası: ortak method-label yardımcısı oluştur ve hem `PlanReview` hem `DataIntake`te
kullan; conflict bloğunu değişken listesinin üstüne kanıt, veri/belge türü, planner maliyeti ve iki
seçim düğmesiyle koy; sonra `StudyBrief`te `fromDocument` alan setini tutup insan düzenlemesinde
rozet ile kanıtı düşür. Ardından hedefli test → desktop tam paket → typecheck → Python tam paket →
`git diff --check`; Task 10 commitinden sonra bütün-dal incelemesi.

Dal: `feat/methodology-matching` (worktree `.worktrees/methodology-intake`; worktree adı eski
dalın adını taşıyor, **dal adına bakın**). Base `1be5ebe`.
Yöntem: subagent-driven, her task'tan sonra inceleme, sonda **zorunlu** tam dal incelemesi
(Erdem'in kararı). Uygulayan ile denetleyen ayrı — Plan 1'in ölçülmüş dersi.
Ledger — **tek doğru kaynak**: `.superpowers/sdd/2026-08-24-metodoloji-eslestirme-plan2/progress.md`
(git-ignored; `git clean -fdx` onu siler, o zaman `git log`'dan kurtarın).
Son temiz Task 9 kapısı: **326 Python + 1 skip** (Task 8 sonrası), **74/74 desktop**, typecheck ve
`git diff --check` temiz. Son commit `4565c4e`; çalışma ağacındaki iki dosya kasıtlı RED testlerdir.

| Task | Durum |
|---|---|
| 1 — Belgenin evi (`projects.py`) | ✅ complete (`1be5ebe..268f3ca`), 1 fix turu |
| 2 — Servis yüzeyi (`app.py`) | ✅ complete (`268f3ca..6e5b1d1`), 1 fix turu, 285 passed |
| 3 — Renderer köprüsü | ✅ complete (`6e5b1d1..066be79`), 1 fix turu (ruling), 70/70 desktop |
| 4 — Eşleştirme sözleşmesi | ✅ complete (`066be79..a12d332`), fix turu gerekmedi, 287 passed |
| 5 — Kavram çıkarımı (`rule.py`) | ✅ complete (`a12d332..b92a292`, 304 passed), 5 fix turu |
| 6 — Değişken eşleştirme | ✅ complete (`6323241`, 314 passed) |
| 7 — Veri/doküman çelişkisi | ✅ complete (`a0c836f`, 323 passed + 1 skip) |
| 8 — Planner ile maliyetleme | ✅ complete (`f6bcf84`, 326 passed + 1 skip; desktop 71/71) |
| 9 — İnsan onayı semantiği | ✅ complete (`4565c4e`, desktop 74/74 + typecheck) |
| 10 — Conflict ekranı + rozet düşürme | 🔴 RED testleri yazıldı; üretim kodu bekliyor |

### (eski kayıt — tarihsel) Task 5'in başlangıçtaki kusur analizi

**Brief'in verdiği `_concepts` kodu kendi testini geçmiyor.** Sebep Türkçe'nin fiil-sonu yapısı:
*"Modeller yaş, cinsiyet ve VKİ **için düzeltildi**"* — kalıp (`düzeltildi`) cümlenin **sonunda**,
kavramlar ise **öncesinde**. Planın ileriye-bakan kuyruk araması bu cümlede yapısal olarak boş
döner. İngilizce (`adjusted for X, Y, Z`) ileriye bakar, Türkçe geriye — plan bunu görmemiş.

Implementer'ın çözümü: geriye-doğru span ayrıştırma + cümlenin **öznesini** dışlayan dar, kapalı
bir stopword listesi (`_ADJUSTMENT_SUBJECT`). Ayrıca brief'in hiç kullanılmayan `_CONNECTORS`
regex'ini atmış ve `_design`'ın zaten yaptığı `original_text` evidence-offset remap'ini eklemiş
(brief bunu atlamıştı).

**İncelemede özellikle denetlenecek üç şey:**
1. **Kalıplar fazla geniş mi?** Plan 1'in ölçülmüş kusuru, geniş kalıbın *başka bir çalışmadan
   yapılan alıntıyı* makalenin kendi beyanı sanmasıydı.
   `test_a_sentence_without_a_concept_pattern_yields_nothing` bunun bekçisi.
2. **Geriye-doğru ayrıştırma + stopword listesi ölçülmemiş bir genellemedir** ve implementer bunu
   açıkça böyle işaretledi (doğru davranış). Tek bir test cümlesinden genelleme yapıldı; inceleme
   bu genellemenin nerede yanlış eşleşeceğini aramalı.
3. **Çıkarım kalitesi ölçülmedi ve bu planda ölçülemez** (gold set Plan 3'te). Kodda, yorumda veya
   raporda ölçülmemiş doğruluk iddiası varsa bulgu sayılır.

**2. Merge sonrası hâlâ açık:** operatör GUI kabul testi (madde 4/3) koşulmadı.

**2b. Task 6 dispatch'ine taşınacak ertelenmiş bulgu:** `extractors/contracts.py:114`
`column_summaries` docstring'i `sorted()`'ın **determinizm** gerekçesini taşımıyor. Dict'ler zaten
ekleme sırasını koruduğu için ileride biri sortu "sadeleştirip" silebilir ve eşitlik bozucu sıra
sessizce kırılır → aynı girdi farklı plan digest'i verebilir. (Task 5 dispatch'ine de eklendi;
Task 5 raporu bunu yaptığını söylüyorsa inceleme teyit etsin, yoksa Task 6'ya taşıyın.)

**3. Plan 3'ü yaz** (spec §7-§8): blocking sözlüğü + gold set + ölçüm + `LocalExtractor`.
Motor seçimi **ölçümsüz yapılmayacak**. Ollama kurulu ve ayakta, **yüklü model yok**
`[ÖLÇÜM 2026-08-24]`.

**Push durumu:** Hiçbir şey push edilmedi. `codex/biostat-studio` `origin`'den ayrışmış
(remote'ta 2 docs-only commit: `6fab78e`, `639e7aa`); push öncesi çekilmeli.
