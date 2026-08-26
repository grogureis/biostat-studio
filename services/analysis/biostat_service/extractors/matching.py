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

# KALİBRE EDİLMEMİŞ (doğrulanmadı). Gold set Plan 3'te kuruluyor. Yanlış
# olmasının bedeli asimetrik ve bilinçli olarak yükseğe eğildi: eşiğin
# ALTINDAKİ her eşleşme "düşük güven" bloğuna düşer, toplu kabul düğmesinin
# dışında kalır ve kullanıcıya tek tek sorulur (spec §6). Eşik fazla
# yüksekse sonuç daha çok soru, fazla düşükse sessizce yanlış rol — sessizlik
# ve sorular ucuz, uydurulmuş yanıtlar pahalı. Plan 3 ölçümünden sonra bu
# satır güncellenmeli.
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
    # Bir içerme tabanı denendi ("left in right or right in left" ise sabit
    # 0.85) ve gerçek klinik sütun adlarıyla ÖLÇÜLEREK KALDIRILDI: 0.85 >
    # MATCH_THRESHOLD (0.80) olduğu için TEK BAŞINA bir sütunu bir kavrama
    # bağlamaya yetiyordu. Ölçülen yanlış pozitifler (hepsi tam 0.850
    # skorluyordu):
    #   "yaş" (yaş)      ↔ "yasam_suresi" (sağkalım süresi — alakasız)
    #   "hasta" (hasta)  ↔ "hastane_kodu" (hastane kodu — alakasız)
    #   "smoking"        ↔ "nonsmoking_status" (KUTUPLUĞU TERS ÇEVİRİYOR)
    # Üstelik brief'in kendi başlık örneğinde İŞE YARAMIYORDU: "otuz gunluk
    # mortalite orani" ↔ "mortalite_30g" içerme koşulunu hiç sağlamıyor,
    # skor salt SequenceMatcher ratio'suyla 0.500'de kalıyordu — yani taban
    # hem gereksiz yere izin veriyor hem de asıl hedef vakada işe yaramıyordu.
    # GERİ EKLEMEYİN: yerine uzunluk-ölçekli bir içerme skoru ya da bir
    # token-örtüşme sezgisi icat etmek de aynı tuzak — kalibrasyon Plan 3'ün
    # gold set'inin işi, bu motorun değil (Task 5'in beş turda öğrendiği
    # ders: sessizlik ve soru ucuz, uydurulmuş skor pahalı).
    return SequenceMatcher(None, left, right).ratio()


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
