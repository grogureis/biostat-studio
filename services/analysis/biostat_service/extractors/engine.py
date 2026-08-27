"""Primary-local extraction policy with an always-available rule fallback."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from ..methodology_intake import MethodologyDocument
from .contracts import (
    BriefProposal,
    ColumnSummary,
    MethodologyExtractor,
    RoleProposal,
)
from .ollama import LocalExtractionError


@dataclass(frozen=True)
class EngineStatus:
    requested: str
    used: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class ExtractionRun:
    brief: BriefProposal
    status: EngineStatus


@dataclass(frozen=True)
class VariableRun:
    proposals: tuple[RoleProposal, ...]
    status: EngineStatus


def _warnings(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        for warning in group:
            if warning not in merged:
                merged.append(warning)
    return tuple(merged)


def _merge_briefs(local: BriefProposal, rule: BriefProposal) -> BriefProposal:
    return BriefProposal(
        title=local.title or rule.title,
        question=local.question or rule.question,
        hypothesis=local.hypothesis or rule.hypothesis,
        design=local.design or rule.design,
        outcome_concepts=local.outcome_concepts or rule.outcome_concepts,
        exposure_concepts=local.exposure_concepts or rule.exposure_concepts,
        covariate_concepts=local.covariate_concepts or rule.covariate_concepts,
        warnings=_warnings(local.warnings, rule.warnings),
    )


def _merge_roles(
    local: tuple[RoleProposal, ...], rule: tuple[RoleProposal, ...]
) -> tuple[RoleProposal, ...]:
    rule_by_column = {item.column: item for item in rule}
    local_by_column = {item.column: item for item in local}
    columns = sorted(set(rule_by_column) | set(local_by_column))
    merged: list[RoleProposal] = []
    for column in columns:
        local_item = local_by_column.get(column)
        rule_item = rule_by_column.get(column)
        merged.append(
            RoleProposal(
                column=column,
                role=(local_item.role if local_item and local_item.role else None)
                or (rule_item.role if rule_item else None),
                kind=(local_item.kind if local_item and local_item.kind else None)
                or (rule_item.kind if rule_item else None),
            )
        )
    return tuple(merged)


class MethodologyEngine:
    """Run local extraction atomically, falling back without failing intake."""

    def __init__(self, local: MethodologyExtractor, rule: MethodologyExtractor):
        self.local = local
        self.rule = rule

    def _fallback_status(self, reason: str) -> EngineStatus:
        return EngineStatus(
            requested=self.local.name,
            used=self.rule.name,
            fallback_reason=reason,
        )

    def _local_available(self) -> bool:
        try:
            return self.local.available()
        except LocalExtractionError:
            return False

    @staticmethod
    def _reason(exc: Exception) -> str:
        if isinstance(exc, LocalExtractionError):
            return exc.code
        return "local_llm_invalid_response"

    def extract(self, document: MethodologyDocument) -> ExtractionRun:
        rule_brief = self.rule.extract_brief(document)
        if not self._local_available():
            return ExtractionRun(
                rule_brief, self._fallback_status("local_llm_unavailable")
            )
        try:
            local_brief = self.local.extract_brief(document)
        except (LocalExtractionError, ValidationError, ValueError) as exc:
            return ExtractionRun(rule_brief, self._fallback_status(self._reason(exc)))
        return ExtractionRun(
            _merge_briefs(local_brief, rule_brief),
            EngineStatus(requested=self.local.name, used=self.local.name),
        )

    def variables(
        self,
        document: MethodologyDocument,
        columns: tuple[ColumnSummary, ...],
    ) -> VariableRun:
        rule_brief = self.rule.extract_brief(document)
        rule_roles = self.rule.match_variables(document, rule_brief, columns)
        if not self._local_available():
            return VariableRun(
                rule_roles, self._fallback_status("local_llm_unavailable")
            )
        try:
            local_brief = self.local.extract_brief(document)
            merged_brief = _merge_briefs(local_brief, rule_brief)
            local_roles = self.local.match_variables(document, merged_brief, columns)
        except (LocalExtractionError, ValidationError, ValueError) as exc:
            return VariableRun(rule_roles, self._fallback_status(self._reason(exc)))
        return VariableRun(
            _merge_roles(local_roles, rule_roles),
            EngineStatus(requested=self.local.name, used=self.local.name),
        )
