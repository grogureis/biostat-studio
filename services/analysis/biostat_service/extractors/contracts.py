"""Shared proposal contracts for every methodology extraction engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proposal:
    """One machine-suggested value, always carrying its own evidence."""

    value: str
    confidence: float
    evidence: str | None = None
    evidence_offset: int | None = None
    source: str = "rule"


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
