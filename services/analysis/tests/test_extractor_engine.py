"""Selection and fallback policy for methodology extraction engines."""

from __future__ import annotations

from biostat_service.extractors.contracts import (
    BriefProposal,
    ColumnSummary,
    Proposal,
    RoleProposal,
)
from biostat_service.extractors.engine import MethodologyEngine
from biostat_service.extractors.ollama import LocalExtractionError
from biostat_service.methodology_intake import MethodologyDocument


def document() -> MethodologyDocument:
    text = "Methods\nA cohort study evaluated mortality after treatment."
    return MethodologyDocument(
        source_sha256="0" * 64,
        source_format="txt",
        text=text,
        char_count=len(text),
        truncated=False,
        warnings=(),
    )


def proposal(value: str, source: str) -> Proposal:
    return Proposal(
        value=value,
        confidence=0.79,
        source=source,
        evidence="cohort study",
        evidence_offset=10,
    )


class FakeExtractor:
    def __init__(
        self,
        name: str,
        brief: BriefProposal,
        roles: tuple[RoleProposal, ...] = (),
        *,
        available: bool = True,
        error: Exception | None = None,
    ):
        self.name = name
        self.brief = brief
        self.roles = roles
        self.is_available = available
        self.error = error

    def available(self) -> bool:
        return self.is_available

    def extract_brief(self, _document: MethodologyDocument) -> BriefProposal:
        if self.error is not None:
            raise self.error
        return self.brief

    def match_variables(
        self,
        _document: MethodologyDocument,
        _concepts: BriefProposal,
        _columns: tuple[ColumnSummary, ...],
    ) -> tuple[RoleProposal, ...]:
        if self.error is not None:
            raise self.error
        return self.roles


def test_local_fields_win_and_rule_fields_fill_only_local_gaps() -> None:
    local = FakeExtractor(
        "local:qwen2.5:14b",
        BriefProposal(
            title=proposal("Local title", "local:qwen2.5:14b"),
            outcome_concepts=(proposal("mortality", "local:qwen2.5:14b"),),
        ),
    )
    rule = FakeExtractor(
        "rule",
        BriefProposal(
            title=proposal("Rule title", "rule"),
            design=proposal("cohort", "rule"),
            outcome_concepts=(proposal("death", "rule"),),
            warnings=("no_method_section",),
        ),
    )

    run = MethodologyEngine(local=local, rule=rule).extract(document())

    assert run.status.requested == "local:qwen2.5:14b"
    assert run.status.used == "local:qwen2.5:14b"
    assert run.status.fallback_reason is None
    assert run.brief.title.value == "Local title"
    assert run.brief.design.value == "cohort"
    assert [item.value for item in run.brief.outcome_concepts] == ["mortality"]
    assert run.brief.warnings == ("no_method_section",)


def test_unavailable_local_model_returns_rule_with_a_stable_reason() -> None:
    local = FakeExtractor("local:qwen2.5:14b", BriefProposal(), available=False)
    rule = FakeExtractor(
        "rule", BriefProposal(design=proposal("cohort", "rule"))
    )

    run = MethodologyEngine(local=local, rule=rule).extract(document())

    assert run.brief.design.source == "rule"
    assert run.status.used == "rule"
    assert run.status.fallback_reason == "local_llm_unavailable"


def test_invalid_local_response_returns_rule_without_leaking_the_error() -> None:
    local = FakeExtractor(
        "local:qwen2.5:14b",
        BriefProposal(),
        error=LocalExtractionError("local_llm_invalid_response"),
    )
    rule = FakeExtractor(
        "rule", BriefProposal(design=proposal("cohort", "rule"))
    )

    run = MethodologyEngine(local=local, rule=rule).extract(document())

    assert run.status.fallback_reason == "local_llm_invalid_response"
    assert run.status.used == "rule"


def test_local_variable_fields_win_while_rule_can_supply_a_missing_kind() -> None:
    local = FakeExtractor(
        "local:qwen2.5:14b",
        BriefProposal(outcome_concepts=(proposal("mortality", "local:qwen2.5:14b"),)),
        (
            RoleProposal(
                column="outcome",
                role=proposal("outcome", "local:qwen2.5:14b"),
            ),
        ),
    )
    rule = FakeExtractor(
        "rule",
        BriefProposal(),
        (
            RoleProposal(
                column="outcome",
                role=proposal("covariate", "rule"),
                kind=proposal("categorical", "rule"),
            ),
        ),
    )
    columns = (ColumnSummary("outcome", "continuous", 100, 100),)

    run = MethodologyEngine(local=local, rule=rule).variables(document(), columns)

    assert run.status.used == "local:qwen2.5:14b"
    assert len(run.proposals) == 1
    assert run.proposals[0].role.value == "outcome"
    assert run.proposals[0].role.source == "local:qwen2.5:14b"
    assert run.proposals[0].kind.value == "categorical"
    assert run.proposals[0].kind.source == "rule"


def test_variable_matching_falls_back_as_one_atomic_run() -> None:
    local = FakeExtractor(
        "local:qwen2.5:14b",
        BriefProposal(),
        error=LocalExtractionError("local_llm_unavailable"),
    )
    rule = FakeExtractor(
        "rule",
        BriefProposal(),
        (RoleProposal(column="outcome", role=proposal("outcome", "rule")),),
    )

    run = MethodologyEngine(local=local, rule=rule).variables(
        document(), (ColumnSummary("outcome", "continuous", 100, 100),)
    )

    assert run.status.used == "rule"
    assert run.status.fallback_reason == "local_llm_unavailable"
    assert run.proposals[0].role.source == "rule"
