# Metodoloji dokümanından çıkarım — tasarım

**Tarih:** 2026-08-24
**Durum:** Tasarım onaylandı, implementasyon planı yazılmadı
**Oturum:** biostat-studio-app-8f (Erdem ile birlikte tasarlandı, biostat-studio-app-1b dış görüş verdi)

---

## 1. Amaç

Kullanıcı bir **metodoloji/proje dokümanı** yükler; program çalışma özetini (`StudyBrief`)
ve Excel yüklendiğinde değişken rollerini önerir. Kullanıcı önerileri görür, çelişkileri
çözer, onaylar; ardından mevcut analiz planı üretilir.

Hedef, kullanıcıya istatistik öğretmek değil: **her kararın sonucunu görünür kılmak.**
İstatistik teknik planlama yeterliliği olmayan bir araştırmacı, seçimlerinin hangi analize
götürdüğünü görerek yeterli bir analiz kurabilmeli.

## 2. Motivasyon — ölçülmüş bulgular

Bu tasarımın gerekçesi kolaylık değil, ölçülmüş iki kusur.

### Bulgu A — kodlanmış kategorikler sessizce `continuous` oluyor `[ÖLÇÜM 2026-08-24]`

`data_intake.py:151` — `numeric_ratio == 1.0` → `kind = "continuous"`.

`infer_variable` yalnızca sütun düzeyi istatistiksel özellikleri kullanıyor. Ölçüm:

| Sütun | Üretilen `kind` | Doğrusu |
|---|---|---|
| `evre` (1,2,3,4) | `continuous` | `categorical` |
| `egitim_duzeyi` (1–5) | `continuous` | `categorical` |
| `merkez_no` (1–8) | `continuous` | `categorical` |
| `evre_metin` (I,II,III,IV) | `categorical` | ✓ |
| `cinsiyet` (0/1) | `binary` | ✓ |

Sonucu `planner.py:427`'de: sürekli maruziyet + sürekli sonuç →
`PlanChoice("pearson_or_spearman")`. Doğrusu `choose_group_method(continuous, 4)` →
**Welch ANOVA**. Yani korelasyon üretiliyor, ANOVA gerekiyorken.

`DataIntake.tsx:81` her rolü `confirmed: true` işaretlediği için kullanıcıya **hiç
sorulmuyor**. Onaylanmış-tür kapısı bu durumda hiç devreye girmiyor.

Veri, `1,2,3,4`'ün evre mi ölçüm mü olduğunu bilemez. **Bunu yalnızca doküman bilir.**
Özelliğin asıl gerekçesi budur.

### Bulgu B — engelleyici kodlar hiç gösterilmiyor `[ÖLÇÜM 2026-08-24]`

`planner.py` 20 farklı `blocking_errors` kodu üretebiliyor:

```
covariates_without_exposure · missing_pair_id_variable · multiple_pair_id_variables
multilevel_exposure_adjustment_unsupported · multiple_exposures_unsupported
not_applicable · not_applicable_single_primary_analysis
unsupported_or_unconfirmed_design · unsupported_outcome_count
unsupported_repeated_adjustment · unsupported_repeated_design
unsupported_repeated_outcome
unknown_variable:X · unconfirmed_{role}:X · invalid_{role}_role:X
unsupported_{role}_kind:X · invalid_pair_id_variable:X · unknown_pair_id_variable:X
unconfirmed_pair_id_variable:X · invalid_pair_id_role:X · invalid_pair_id_kind:X
```

`PlanReview.tsx:66` `blocking` dizisini **hiç render etmiyor**; kullanıcı yalnızca
*"Bu planı onaylamadan önce engelleyici maddeleri çözün"* görüyor. Hangi madde, neden,
nasıl çözülür — yok.

Otomatik doldurma bunu ağırlaştırır: kullanıcı brief'i kendi yazmadığı için tıkandığında
hiçbir fikri olmaz.

## 3. Değişmezler

Aşağıdakiler bu işte **değişmez**. Herhangi birine dokunmak, tasarımın ihlalidir.

- `planner.py` karar mantığı (`_primary_choice`, `build_plan`, `choose_group_method`)
- `analyses.py`, `power.py`, `reporting.py`
- Plan determinizmi: aynı girdi → aynı metot → aynı digest
- Fail-closed davranışı: desteklenmeyen yapı `BlockingPlanError`
- Çevrimdışı varsayılan: hasta verisi hiçbir koşulda makineden çıkmaz
- Renderer'ın dosya yolunu görmemesi (capability token deseni)

**Sınır ilkesi:** LLM `planner`'ın *önüne* girer, *yerine* değil.
Metin → etiket işi dil anlamadır (LLM). Etiket → metot işi kuraldır (deterministik).

Bu sınır bir konvansiyon değil, yapısal olgu:
`build_plan(brief, profile, roles)` imzasında doküman metni, LLM çıktısı veya güven
skoru yoktur. `planner` bir LLM'in varlığını öğrenemez.

---

## 4. Bölüm 1 — Doküman alımı

### Akış

```
renderer → bridge.selectMethodologyDocument()      ← renderer yolu ASLA görmez
  main.ts → dialog.showOpenDialog(filtre)
  main.ts → pathCapabilities.issue("methodology-document", path) → opak token
renderer → POST /v1/methodology/extract { source_capability: token }
  api-proxy.ts → consume(token, "methodology-document") → gerçek yolu enjekte
  Python → dosyayı okur
```

`main.ts:59-71` + `api-proxy.ts:43-51`'deki mevcut Excel deseninin birebir kopyası.
Yeni güvenlik yüzeyi açılmıyor, var olan bir scope genişletiliyor.

### Karar A — metin çıkarma Python'da

Gerekçe: `python-docx` zaten bağımlılıkta (1.2.0, `reporting.py` kullanıyor); Excel de
aynı yoldan gidiyor; renderer'ın yolu görmeme garantisi korunuyor.

### Karar B — doküman bir kez okunur, metni oturumda tutulur

Capability token'ları tek kullanımlık (`api-proxy.ts:47`, `consume` siler). Doküman iki
aşamada gerekli: (1) brief doldurma, (2) rol atama. Excel bunu iki token vererek çözmüş
(`main.ts:69-70`); doküman için daha temiz yol, çıkarılan metni `MethodologyDocument`
olarak servis oturumunda saklamak. İkinci aşama dosyaya hiç dokunmaz.

### Karar C — format kapsamı

| Format | Bağımlılık |
|---|---|
| `.docx` | `python-docx` — mevcut |
| `.txt` / `.md` | yok |
| `.pdf` | **`pypdf>=5,<6`** — yeni, ~1 MB, saf Python, PyInstaller uyumlu |

**Taranmış PDF:** `pypdf` metin katmanı olmayan PDF'te sessizce boş string döner. Bu
tespit edilip kullanıcıya açıkça bildirilir — *"Bu PDF taranmış görünüyor, içinde
okunabilir metin yok."* Sessizce boş çıkarımla devam edilmez. Fail-closed.

PyMuPDF reddedildi: C bağımlılığı + AGPL, paketlemeyi ve dağıtımı ağırlaştırıyor.

### Karar D — sınırlar ve gerekçeleri

- **Dosya boyutu 25 MB.** Üstündeki bir metodoloji dokümanı ya gömülü görsellerden
  ibarettir ya yanlış dosyadır; erken ve net reddetmek modele çöp yollamaktan iyi.
- **Çıkarılan metin 200.000 karakter** (~50 sayfa yoğun metin). Bir tezin metodoloji
  bölümü bile altında kalır. Aşılırsa kırpılır **ve kullanıcıya bildirilir** — sessiz
  kırpma yok.
- Modele giden metin bütçesi ayrı ve çok daha dar (Bölüm 2, bölüm bulucu).

### Dokunulan yüzey

| Katman | Değişiklik |
|---|---|
| `path-capabilities.ts` | `PathCapabilityScope`'a `"methodology-document"` |
| `main.ts` | `biostat:select-methodology-document` IPC + dialog filtresi |
| `bridge.ts`, `preload.ts` | `selectMethodologyDocument()` |
| `api-proxy.ts` | Allowlist'e `POST /v1/methodology/extract` + capability enjeksiyonu |
| `client.ts` | `extractMethodology()` |
| `pyproject.toml` | `pypdf>=5,<6` |
| **yeni** `methodology_intake.py` | Metin çıkarma, sınırlar, taranmış PDF tespiti |

---

## 5. Bölüm 2 — Çıkarım arayüzü

### Üç ayrı iş

| # | İş | Girdi → Çıktı | Motor |
|---|---|---|---|
| 1 | Çıkarım | Doküman metni → kavramlar | LLM |
| 2 | Eşleştirme | Kavramlar × sütun adları → rol atamaları | Bulanık eşleştirme + LLM |
| 3 | Tür (`kind`) | Veri → sürekli/ikili/kategorik/tarih/tanımlayıcı | **Deterministik** |

3 LLM'e verilmez: veri, bir sütunda kaç benzersiz değer olduğu konusunda yalan söylemez.
**Ama** doküman veriden gelen türü *tek yönde düzeltebilir*: "bu sayısal sütun aslında
kategoriktir" (Bulgu A).

### Sözleşme

```python
class MethodologyExtractor(Protocol):
    name: str                      # "rule" | "local:qwen2.5:14b" | "cloud:..."
    def available(self) -> bool: ...
    def extract_brief(self, doc: MethodologyDocument) -> BriefProposal: ...
    def match_variables(
        self,
        doc: MethodologyDocument,
        concepts: BriefProposal,
        columns: tuple[ColumnSummary, ...],
    ) -> tuple[RoleProposal, ...]: ...


@dataclass(frozen=True)
class Proposal[T]:
    value: T
    confidence: float            # 0..1
    evidence: str | None         # dokümandan birebir alıntı
    evidence_offset: int | None  # metindeki konum → UI vurgular
    source: str                  # üreten motor


@dataclass(frozen=True)
class ColumnSummary:
    name: str
    kind: str            # data_intake.infer_variable çıktısı
    unique_values: int
    non_missing: int
    # HÜCRE DEĞERİ YOK — bilinçli
```

`ColumnSummary`'de hücre değeri bulunmaması bilinçlidir: bulut motoru bir gün açılırsa
hasta verisi **yapısal olarak** gidemez. Gizlilik bir politika değil, tip imzası.

### Bağlam bütçesi — bölüm bulucu

200k karakter hiçbir yerel modelin bağlamına sığmaz. **Deterministik bölüm bulucu**
üç motorun da önünde durur:

- `Yöntem`, `Gereç ve Yöntem`, `Methods`, `Materials and Methods`,
  `İstatistiksel Analiz`, `Statistical Analysis` başlıklarını arar
- Bu bölümleri + özet/abstract'ı çıkarır
- Bulamazsa ilk N karakteri alır **ve kullanıcıya bildirir**

Motordan bağımsız olması şart: yoksa gold set ölçümü motoru değil, kırpmayı ölçer.

### `RuleExtractor` — taban çizgisi

LLM taklidi yapmaz, dürüstçe az şey yapar:

- **Tasarım:** TR+EN anahtar kelime sözlüğü (`retrospektif kohort`, `olgu-kontrol`,
  `kesitsel`, `randomize`, `case-control`, …)
- **Sonuç/maruziyet:** kalıp eşleştirme (`birincil sonlanım`, `primary outcome`,
  `bağımlı değişken`, `maruziyet`)
- **Soru/hipotez:** ilgili başlık altındaki ilk paragraf
- **Eşleştirme:** normalize edilmiş bulanık eşleştirme — Türkçe karakter katlaması,
  kısaltma sözlüğü (`HbA1c`↔`hba1c`, `sistolik KB`↔`sistolik_kan_basinci`)

Emin olmadığı yeri **boş bırakır, uydurmaz.** Değeri iki katlı: kurulum gerektirmeyen
zemin, ve LLM'in ne kattığını ölçecek taban çizgisi.

### Motorlar

| Motor | Durum |
|---|---|
| `RuleExtractor` | Her zaman mevcut, kurulum yok |
| `LocalExtractor` | Ollama, `localhost:11434` yoklanır — **varsayılan LLM** |
| `CloudExtractor` | Ayrı ve açık opt-in; varsayılan değil |

Ölçüm `[ÖLÇÜM 2026-08-24]`: makinede 24 GB RAM, Apple M5 Pro, Ollama kurulu ve servis
ayakta, **yüklü model yok**. Model seçimi Bölüm 5'teki ölçümle yapılır; şimdiden
taahhüt edilmez.

Model `.app` içine gömülmez: 2–6 GB, notarization ve dağıtım ağırlaşır, ve ölçmeden
taahhüt olur. Ölçüm belirli bir modeli işaret ederse gömme o zaman tartışılır.

---

## 6. Bölüm 3 — Onay katmanı ve çelişki çözümü

### Çelişkinin bedelini `planner` hesaplar

Çelişkili değişkende iki olası tür var. **Her ikisi için `build_plan` gerçekten çağrılır**
ve kullanıcıya sonuç gösterilir:

```
⚠  evre

   Veriniz     : 4 farklı sayısal değer (1, 2, 3, 4) — ölçüm gibi görünüyor
   Dokümanınız : "Hastalar TNM evresine göre I–IV olarak sınıflandırıldı."   [s.3]

   Öneri: Kategorik (4 düzey)
   Neden: Doküman evreyi bir sınıflandırma olarak tanımlıyor; 1–4 sayıları
          sıra etiketi, ölçüm değil.

   Bu seçim analizi değiştirir:
     Kategorik seçilirse →  Welch ANOVA (4 grup karşılaştırması)
     Sürekli seçilirse   →  Pearson/Spearman korelasyonu

   [ Kategorik — önerilen ]   [ Sürekli ]
```

Alt satırdaki metotlar **LLM tahmini değil**, `planner.py`'nin iki farklı girdiyle
verdiği gerçek cevabı. Kullanıcının istatistik bilmesi gerekmez; seçimin bedelini,
analizi çalıştıracak kodun kendisi söyler.

### İş bölümü

| Parça | Kim | Neden |
|---|---|---|
| Çelişki tespiti | Deterministik kod | `data_kind != document_kind` — karşılaştırma |
| Sonucun hesabı | `planner.build_plan` | Analizi çalıştıracak kodun ta kendisi |
| Açıklama + öneri | LLM | Laik dille anlatır ve mantıklı olanı önerir |
| **Karar** | **Kullanıcı** | Kapı burada |

**Bozulmadan çalışma:** LLM yoksa tespit ve sonuç hesabı **aynen çalışır**; yalnızca
açıklama şablon metne düşer. Özellik LLM'e bağımlı değil — LLM onu anlaşılır kılıyor.

### `confirmed` bayrağının anlamı

- `confirmed: false` → makine önerdi, insan bakmadı
- `confirmed: true` → **insan gördü ve onayladı**

`contracts.py:VariableRole` zaten `confirmed: bool = False` varsayılanıyla duruyor;
sözleşme doğruydu, `DataIntake.tsx:81` onu boşa çıkarıyordu. Düzeltilir.

### Toplu kabul

**"Kalan N değişkeni olduğu gibi kabul et"** düğmesi vardır — ancak:

- Çelişkili olanlar bu düğmenin **dışında** kalır
- Güveni eşiğin altında olanlar **dışında** kalır

Bu ikisi tek tek onaylanır. Kullanıcının dikkati riskin olduğu yere odaklanır; kolaylık
tam olarak risksiz kısımda verilir. (Eşik değeri Bölüm 5 ölçümünden sonra belirlenir.)

### Akış kilidi

```
Doküman → brief önerileri → kullanıcı onayı
                                    ↓
Excel → veri profili + doküman eşleştirmesi
                                    ↓
                        çelişki var mı?
                       ╱              ╲
                    yok               var
                     ↓                 ↓
                     ↓        LLM açıklar + önerir
                     ↓        kullanıcı seçer  ←── plan üretimi BURADA KİLİTLİ
                     ╲              ╱
                      ↓            ↓
                  dataApproved = true
                          ↓
                  planner.build_plan()   ← değişmedi
```

Çözülmemiş çelişki varken `dataApproved` **true olmaz**; `App.tsx:206`'daki mevcut kilit
plan adımını zaten kapalı tutar. Yeni kilit icat edilmiyor, var olan besleniyor.

### Ekranlar

**01 Çalışma özeti** — Excel panelinin muadili doküman paneli. Alanlar önerilerle dolar;
her alanın yanında *"dokümandan"* işareti, tıklayınca kaynak cümle. Kullanıcı alanı elle
düzenlerse işaret düşer, alan "sizin" olur.

**02 Veri ve değişkenler** — çelişkili ve düşük güvenli değişkenler listenin **üstünde
ayrı blokta**. Gerisi normal listede, önerileri ve kanıtlarıyla.

---

## 7. Bölüm 4 — `planner` sınırı ve blocking sözlüğü

### Sınır

Yapısal (bkz. §3). Tek gerçek risk, LLM'in `brief` alanlarını doldurup kullanıcının
onaylamadan geçmesi — Bölüm 3'teki `confirmed` kapısı bunu kapatır.

### Blocking sözlüğü — LLM değil

20 kod sonlu ve sabit bir küme. Her birine **elle yazılmış** TR/EN açıklama + somut
düzeltme yolları. LLM'in katkısı sıfır, uydurma riski gerçek.

Örnek:

```
multilevel_exposure_adjustment_unsupported
  Ne oldu : "evre" 4 düzeyli ve aynı anda yaş/cinsiyet düzeltmesi istendi.
            Bu program çok düzeyli bir maruziyeti kovaryatlarla birlikte
            modelleyemiyor.
  Seçenekler:
    · Kovaryatları çıkarıp düzeltmesiz 4 grup karşılaştırması yapın (Welch ANOVA)
    · Evreyi iki düzeye indirin (örn. erken / ileri) ve düzeltmeyi koruyun
    · Bu analiz için istatistik desteği alın — program bu modeli kurmuyor
```

Üçüncü seçenekteki dürüstlük zorunludur: **program yapamadığını yapabilirmiş gibi
göstermemeli.** `planner`'ın fail-closed refleksi ekranda da fail-closed kalır.

Sık karşılaşılacak kodlar ve gerçek karşılıkları:

| Kod | Gerçek hayatta |
|---|---|
| `multiple_exposures_unsupported` | İki maruziyeti aynı anda incelemek |
| `covariates_without_exposure` | Sadece kovaryat düzeltmesi istemek |
| `multilevel_exposure_adjustment_unsupported` | 3+ düzeyli maruziyet + yaş/cinsiyet düzeltmesi |
| `unsupported_repeated_adjustment` | Tekrarlı ölçüm + kovaryat |

Dördü de metodolojik olarak makul çalışmalardır; `planner` 12 metotla sınırlı olduğu için
yapamıyor.

### Denetim kaydı

`AnalysisProvenance`'a eklenir: kaynak doküman SHA256, çıkarım motoru adı, hangi alanların
makineden hangilerinin insandan geldiği. Reprodüksiyon iddiası ancak böyle ayakta kalır.

### Dokunulan yüzey

`PlanReview.tsx` — `blocking` dizisi artık render edilir. `planner.py` karar mantığı
değişmez.

---

## 8. Bölüm 5 — Ölçüm düzeneği

### Birincil metrik: metot uyumu

```python
plan_gold  = build_plan(gold_brief,  profile, gold_roles)
plan_motor = build_plan(motor_brief, profile, motor_roles)
uyum = [i.method for i in plan_gold.items] == [i.method for i in plan_motor.items]
```

Alan doğruluğu **birincil metrik değildir** — hataların bedeli eşit değil. Kovaryat
listesinde bir eksik çoğu zaman hiçbir şeyi değiştirmez; sonuç değişkenini yanlış
seçmek analizi tamamen başka yere götürür.

### İkincil: tehlikeli hata oranı

Yanlış **ve** güveni eşiğin üstünde → toplu kabule girer → kullanıcı görmeden geçer.
Sıfıra yakın olmalı. Bu, toplu kabul kararının güvenlik payıdır.

### Üçüncül: yakalama oranı

Motorun "emin değilim" dediği ve gerçekten yanıldığı oran. **Yüksek olması iyi.**

Ayrım: *iyi motor* az yanılır; *güvenli motor* yanıldığında bilir. İnsan onayı zaten
olduğu için ikincisi daha değerli.

Alan bazlı doğruluk (tasarım sınıflandırması, sonuç/maruziyet/kovaryat P/R) tanı amaçlı
kaydedilir — "neden kötü" sorusu için, "iyi mi" sorusu için değil.

### Gold set

**Kaynak: PubMed açık erişim (PMC) Methods bölümleri.** İki katman:

| Katman | n | Amaç |
|---|---|---|
| Eleme seti | 30–50 | Zayıf modelleri ucuza ele |
| Kabul seti | 15 | Final karar |

**15 rastgele seçilmez.** 12 desteklenen metot + 4 bilinen engellenen desen
(`multiple_exposures`, `covariates_without_exposure`, `multilevel_exposure_adjustment`,
`repeated_adjustment`) her biri en az bir örnekle temsil edilmeli — yoksa blocking-kod
açıklama yolu hiç test edilmemiş olur.

**Sentetik doküman kullanılmaz.** LLM kendi ürettiği düzgün metni, gerçek araştırmacının
dağınık metninden çok daha kolay okur; sentetik set yalancı iyimser sonuç verir.

Her kayıt: doküman + sütun şeması (**gerçek hasta verisi değil** — ad, `kind`, benzersiz
sayısı) + elle yazılmış doğru cevap.

**Kayda geçen sınırlamalar:**
- n=15'te 1–2 dokümanlık fark gürültüdür. Bu ölçüm "%50 mi %90 mı" ayrımını yapar,
  "%85 mi %90 mı" ayrımını **yapmaz**. Motor seçmeye yeter, eşik ince ayarına yetmez.
- PubMed Methods metinleri hakem sürecinden geçmiş, cilalanmış metinlerdir. Programın
  gerçek girdisi — kullanıcının kendi yazdığı, eksik ve dağınık olabilen doküman —
  **farklı bir dağılımdır.** Ölçüm gerçek kullanımda iyimser çıkabilir. İlk gerçek
  kullanıcı dokümanları geldiğinde set genişletilmelidir.

### Motor matrisi

| Motor | Rolü |
|---|---|
| `rule` | Taban çizgisi |
| `local:qwen2.5:7b` | Aday |
| `local:qwen2.5:14b` | Aday (24 GB'de rahat) |
| `local:qwen2.5:32b` | Aday — Electron+Python ile aynı anda sığar mı `doğrulanmadı` |
| `cloud:*` | **Yalnızca tavan referansı, üründe değil** |

Bulut satırı sadece "yerel model tavana ne kadar yakın" sorusu için ve yalnızca PubMed
kaynaklı dokümanlarda çalıştırılır.

### Tekrarlanabilirlik

`temperature=0` tekrarlanabilirliği **garanti etmez** `[DOKÜMAN]`. Her motor **3 kez**
çalıştırılır, değişkenlik kaydedilir. Kendi kendisiyle tutarsız bir motor tek başına
elenir: denetim kaydı iddiası olan bir üründe tekrarlanmayan çıkarım kabul edilemez.

Koşucu: `scripts/eval-extractors.py` → tablo + JSON.

---

## 9. Fazlama

| Faz | İçerik |
|---|---|
| **1** | Doküman alımı + çıkarım + eşleştirme + onay katmanı + çelişki çözümü + blocking sözlüğü |
| **2** | Planın laik dille açıklanması (metot neden seçildi, varsayımları ne, ihlal edilirse ne olur) |

Ölçüm (Bölüm 5) Faz 1'in içindedir; motor seçimi ölçümsüz yapılmaz.

## 10. Kapsam dışı (YAGNI)

- Yeni istatistik metotları (sağkalım, karışık modeller, çoklu maruziyet) — ayrı iş
- `ordinal` türünün `kind` sözlüğüne eklenmesi — `planner`'ı değiştirir, ayrı karar
- OCR (taranmış PDF) — tespit edilir ve reddedilir, çözülmez
- Modelin `.app` içine gömülmesi — ölçümden sonra tartışılır
- Bulut motorunun üründe varsayılan olması — ayrı ve açık bir karar

## 11. Açık kararlar

| Konu | Ne zaman karara bağlanır |
|---|---|
| Toplu kabul güven eşiği | Bölüm 5 ölçümü sonrası, veriye bakarak |
| Hangi yerel model | Bölüm 5 ölçümü sonrası |
| Bulut motorunun üründe yer alıp almayacağı | Faz 1 teslim sonrası, ayrı karar |

## 12. Bu işten bağımsız, canlı kusurlar

Tasarım sırasında ölçüldü. Bulgu A'nın iki yarısı var ve **bu iş yalnızca birini
çözüyor** — ayrımı karıştırmamak önemli:

1. **Bulgu A-1** (`DataIntake.tsx:81`, `confirmed: true`) — **bu iş çözüyor** (§6).
   Kullanıcı bakmadığı hiçbir role `confirmed` yazılmayacak.
2. **Bulgu A-2** (`data_intake.py:151`, `numeric_ratio == 1.0` → `continuous`) —
   **bu iş çözmüyor.** Tasarım bunu bir *çıkarım kusuru* olarak kabul edip dokümandan
   gelen düzeltmeyle telafi ediyor (§5, §6). Kusurun kendisi yerinde duruyor: dokümanı
   olmayan bir kullanıcı hâlâ sessizce yanlış sınıflandırmayla karşılaşır.
   Klinik veride `evre`/`merkez` gibi kodlu kategorikler çok sık; operatör kabul
   testinde yüksek ihtimalle çıkar. biostat-studio-app-1b bunu Task 8'e taşıdı.
   **Ayrıca öncelendirilmeli** — bu spec'in teslimi onu kapatmaz.
3. **Bulgu B** (`PlanReview.tsx:66`) — engelleyici kodlar render edilmiyor. Bu tasarım
   Bölüm 4'te çözüyor.
