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
  exposure_variables?: string[];
  covariates?: string[];
  pair_id_variable?: string;
  language?: Language;
}

export interface VariableRole {
  name: string;
  role: string;
  kind: string;
  confirmed: boolean;
}

export interface VariableProfile {
  display_name: string;
  kind: string;
  non_missing: number;
  missing: number;
  unique_values: number;
}

export interface DataProfile {
  sheets: string[];
  selected_sheet: string;
  rows: number;
  columns: number;
  missing_cells: number;
  variables: Record<string, VariableProfile>;
  warnings: Array<{ code: string; column: string | null; message: string }>;
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
  revision: string;
  digest: string;
  items: PlanItem[];
  blocking_errors: string[];
  warnings: string[];
}

export type PowerAnalysis =
  | "two_sample_t"
  | "paired_t"
  | "one_way_anova"
  | "two_proportions"
  | "correlation";

export interface PowerRequest {
  analysis: PowerAnalysis;
  solve_for: "power" | "sample_size";
  alpha: number;
  power?: number | null;
  effect_size?: number | null;
  proportion_one?: number | null;
  proportion_two?: number | null;
  sample_size?: number | null;
  groups?: number;
}

export interface PowerResponse {
  analysis: PowerAnalysis;
  solve_for: "power" | "sample_size";
  inputs: Record<string, number>;
  sample_size_unit: "per_group" | "pairs" | "total";
  power: number | null;
  sample_size: number | null;
  per_group_rounded: number | null;
  total_rounded: number | null;
  achieved_power: number | null;
  method: string;
  library_versions: Record<string, string>;
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

export interface AnalysisProvenance {
  data_fingerprint: string;
  plan_version: number;
  exclusions: string[];
  transformations: string[];
  random_seed: number | null;
  library_versions: Record<string, string>;
}

export interface AnalysisResult {
  id: string;
  method: string;
  n: number;
  estimate: number | null;
  p_value: number | null;
  confidence_interval: ConfidenceInterval;
  effect_size: EffectSize;
  provenance: AnalysisProvenance;
  diagnostics: Record<string, unknown>;
  exclusions: string[];
  warnings: string[];
}

export interface ProposalDto {
  value: string;
  confidence: number;
  evidence: string | null;
  evidence_offset: number | null;
  source: string;
}

export interface RoleProposalDto {
  column: string;
  role: ProposalDto | null;
  kind: ProposalDto | null;
}

export interface ConflictDto {
  column: string;
  data_kind: string;
  document_kind: string;
  evidence: string | null;
  evidence_offset: number | null;
  methods_if_document: string[];
  methods_if_data: string[];
  blocked_if_document: string[];
  blocked_if_data: string[];
}

export interface VariableProposalResponse {
  proposals: RoleProposalDto[];
  conflicts: ConflictDto[];
  engine?: MethodologyEngineStatus;
}

export interface MethodologyEngineStatus {
  requested: string;
  used: string;
  fallback_reason: string | null;
}

/** Mirrors BriefProposal in services/analysis/biostat_service/extractors/contracts.py — all eight fields. */
export interface BriefProposalDto {
  title: ProposalDto | null;
  question: ProposalDto | null;
  hypothesis: ProposalDto | null;
  design: ProposalDto | null;
  outcome_concepts: ProposalDto[];
  exposure_concepts: ProposalDto[];
  covariate_concepts: ProposalDto[];
  warnings: string[];
}

export interface MethodologyExtraction {
  source_sha256: string;
  source_format: string;
  /** The bare filename only — never a path. See api-proxy.ts's renderer-path ban. */
  original_name: string;
  char_count: number;
  truncated: boolean;
  /**
   * The full extracted document text. The project that will own this text
   * does not exist yet when extraction happens (it is only created once the
   * Excel workbook arrives), so the renderer carries it in the meantime —
   * see store.ts's `methodology` field.
   */
  text: string;
  warnings: string[];
  brief: BriefProposalDto;
  engine?: MethodologyEngineStatus;
}
