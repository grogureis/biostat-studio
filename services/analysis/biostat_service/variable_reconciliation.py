"""Compare what the data says about a column with what the document says.

This module never decides. It reports a disagreement and — starting Task 8 —
what that disagreement costs, so the user can decide (spec §6).
"""

from __future__ import annotations

from dataclasses import dataclass

from .data_intake import DataProfile
from .extractors.contracts import RoleProposal

# Belgenin veriyi düzeltmesine izin verilen TEK yön (spec §5). Veri, bir
# sütunda kaç benzersiz değer olduğu konusunda yalan söylemez; ama bir
# belge "sürekli ölçüm" ifadesini metaforik ya da başka bir değişken için
# kullanabilir. Bu yüzden ters yön (categorical/binary -> continuous)
# burada YOK: bir kategori asla "aslında sürekliymiş" diye düzeltilmez.
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
