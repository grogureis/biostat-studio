export type StudyDesign =
  | "cross_sectional"
  | "cohort"
  | "case_control"
  | "trial"
  | "repeated";

export type Language = "en" | "tr";

export interface StudyBrief {
  title: string;
  question: string;
  hypothesis: string;
  design: StudyDesign;
  outcome_variables: string[];
  exposure_variables: string[];
  covariates: string[];
  language: Language;
}

export interface VariableRole {
  name: string;
  role: string;
  kind: string;
  confirmed: boolean;
}

export interface PlanItem {
  id: string;
  estimand: string;
  method: string;
  rationale: string;
  required_variables: string[];
  assumptions: string[];
  robust_alternative: string | null;
  multiplicity_strategy: string | null;
  outputs: string[];
  blocking_errors: string[];
  warnings: string[];
}

export interface AnalysisPlan {
  version: number;
  items: PlanItem[];
  blocking_errors: string[];
  warnings: string[];
}

export interface ConfidenceInterval {
  level: number;
  lower: number | null;
  upper: number | null;
}

export interface EffectSize {
  name: string;
  value: number | null;
}

export interface AnalysisResult {
  id: string;
  method: string;
  n: number;
  estimate: number | null;
  p_value: number | null;
  confidence_interval: ConfidenceInterval;
  effect_size: EffectSize;
  diagnostics: Record<string, unknown>;
  exclusions: string[];
  warnings: string[];
}
