"""Shared proposal contracts for every methodology extraction engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..methodology_intake import MethodologyDocument
    from ..data_intake import DataProfile


# Evidence bütçesi. Bir metodoloji bölümündeki uzun bir akademik cümle 200-350
# karakter arasında kalır; 400 rahat bir pay bırakır ve bunun ötesi artık bir
# cümle değil, veri dökümüdür. Evidence HTTP yanıtına konduğu için bu sınır
# aynı zamanda bir gizlilik sınırıdır: noktalama taşımayan bir doküman
# (yapıştırılmış tablo, OCR çıktısı) sınırsız bir fallback ile kendisini
# olduğu gibi geri döndürebilir.
EVIDENCE_MAX_CHARS = 400


@dataclass(frozen=True)
class Proposal:
    """One machine-suggested value, always carrying its own evidence.

    `source` is REQUIRED and deliberately has no default. It is the provenance
    field, and spec §7 makes provenance a shipped promise. A default naming a
    concrete engine ("rule") makes silence indistinguishable from a positive
    claim of rule-engine origin — the one field where a wrong default is a
    false attestation rather than a merely missing value. Proposal is the
    shared multi-engine contract, and a contract's defaults are what future
    engines inherit: a language-model engine that forgets to pass `source` now
    gets a TypeError at construction instead of silently mislabelling its own
    output as deterministic rule output.
    """

    value: str
    confidence: float
    source: str
    evidence: str | None = None
    evidence_offset: int | None = None


@dataclass(frozen=True)
class BriefProposal:
    """Study-brief fields proposed from a methodology document.

    Every field is a suggestion, never a decision: the user confirms each one
    before planner.build_plan is allowed to see it.

    `warnings` carries through whatever select_relevant_text reported about
    the source text (e.g. "no_method_section") so a later UI layer can show
    it to the user instead of it being silently discarded.
    """

    title: Proposal | None = None
    question: Proposal | None = None
    hypothesis: Proposal | None = None
    design: Proposal | None = None
    outcome_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
    exposure_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
    covariate_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


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
