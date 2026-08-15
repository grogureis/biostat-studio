"""Shared request, planning, and result contracts for the local service."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StudyBrief(BaseModel):
    title: str = Field(min_length=1)
    question: str = Field(min_length=5)
    hypothesis: str = Field(min_length=3)
    design: Literal["cross_sectional", "cohort", "case_control", "trial", "repeated"]
    outcome_variables: list[str] = Field(min_length=1)
    exposure_variables: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    language: Literal["en", "tr"] = "en"


class VariableRole(BaseModel):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    confirmed: bool = False


class PlanItem(BaseModel):
    id: str = Field(min_length=1)
    estimand: str = Field(min_length=1)
    method: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_variables: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    robust_alternative: Optional[str] = None
    multiplicity_strategy: Optional[str] = None
    outputs: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    version: int = Field(default=1, ge=1)
    items: list[PlanItem] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfidenceInterval(BaseModel):
    level: float = Field(default=0.95, gt=0, lt=1)
    lower: Optional[float] = None
    upper: Optional[float] = None


class EffectSize(BaseModel):
    name: str = Field(min_length=1)
    value: Optional[float] = None


class AnalysisResult(BaseModel):
    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    n: int = Field(ge=0)
    estimate: Optional[float] = None
    p_value: Optional[float] = Field(default=None, ge=0, le=1)
    confidence_interval: ConfidenceInterval
    effect_size: EffectSize
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
