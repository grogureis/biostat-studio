"""Compare what the data says about a column with what the document says.

This module never decides. It reports a disagreement and — starting Task 8 —
what that disagreement costs, so the user can decide (spec §6).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import AnalysisPlan, StudyBrief, VariableRole
from .data_intake import DataProfile
from .extractors.contracts import RoleProposal
from .planner import build_plan

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
    """Price one hypothetical kind choice without mutating live role state.

    Pricing happens before the human confirmation gate, so every role is
    confirmed only inside this disposable copy. Otherwise both hypothetical
    plans would stop at the same `unconfirmed_*` errors and conceal the
    statistical consequence the user is being asked to decide about.
    """
    candidate = {
        name: role.model_copy(
            update={
                "confirmed": True,
                **({"kind": kind} if name == column else {}),
            }
        )
        for name, role in roles.items()
    }
    return build_plan(brief, profile, candidate)


def price_conflicts(
    brief: StudyBrief,
    profile: DataProfile,
    roles: dict[str, VariableRole],
    conflicts: tuple[Conflict, ...],
) -> tuple[ConflictCost, ...]:
    """Ask the real planner what each choice costs; never predict methods."""
    priced: list[ConflictCost] = []
    for conflict in conflicts:
        with_document = _plan_for(
            brief, profile, roles, conflict.column, conflict.document_kind
        )
        with_data = _plan_for(
            brief, profile, roles, conflict.column, conflict.data_kind
        )
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
