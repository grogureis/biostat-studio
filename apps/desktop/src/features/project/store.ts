import { useReducer } from "react";

import type { AnalysisPlan, AnalysisResult, Language, MethodologyExtraction, StudyBrief } from "../../api/types";
import type { OpenProjectSnapshot } from "../../api/client";

export type WorkflowStep = "study" | "data" | "plan" | "run" | "results" | "report" | "power";

const emptyBrief: StudyBrief = {
  title: "",
  question: "",
  hypothesis: "",
  design: "cohort",
  outcome_variables: [],
  exposure_variables: [],
  covariates: [],
  language: "en",
};

interface ProjectState {
  activeStep: WorkflowStep;
  language: Language;
  brief: StudyBrief;
  dataFile: string | null;
  dataApproved: boolean;
  plan: AnalysisPlan | null;
  planApproved: boolean;
  results: AnalysisResult[];
  methodology: MethodologyExtraction | null;
}

const initialState: ProjectState = {
  activeStep: "study",
  language: "en",
  brief: emptyBrief,
  dataFile: null,
  dataApproved: false,
  plan: null,
  planApproved: false,
  results: [],
  methodology: null,
};

type Action =
  | { type: "step"; value: WorkflowStep }
  | { type: "language"; value: Language }
  | { type: "brief"; value: StudyBrief }
  | { type: "data"; value: string | null }
  | { type: "data_approved" }
  | { type: "plan"; value: AnalysisPlan | null }
  | { type: "plan_approved"; value: boolean }
  | { type: "results"; value: AnalysisResult[] }
  | { type: "methodology"; value: MethodologyExtraction | null }
  | { type: "restore"; value: OpenProjectSnapshot };

function clearDependents(state: ProjectState): ProjectState {
  return { ...state, dataApproved: false, plan: null, planApproved: false, results: [] };
}

function reducer(state: ProjectState, action: Action): ProjectState {
  switch (action.type) {
    case "step": return { ...state, activeStep: action.value };
    case "language": return { ...state, language: action.value };
    case "brief": return clearDependents({ ...state, brief: action.value });
    case "data": return clearDependents({ ...state, dataFile: action.value });
    case "data_approved": return { ...state, dataApproved: true };
    case "plan": return { ...state, plan: action.value, planApproved: false, results: [] };
    case "plan_approved": return { ...state, planApproved: action.value };
    case "results": return { ...state, results: action.value };
    // Deliberately does NOT clearDependents: the document is not a
    // derivative of the brief (unlike "brief" and "data" above), so it must
    // survive brief edits made after the document was extracted.
    case "methodology": return { ...state, methodology: action.value };
    case "restore": return {
      ...state,
      activeStep: action.value.results.length ? "results" : action.value.plan ? "plan" : "data",
      language: action.value.brief.language ?? state.language,
      brief: action.value.brief,
      dataFile: null,
      dataApproved: action.value.roles.length > 0,
      plan: action.value.plan,
      planApproved: action.value.approved_plan,
      results: action.value.results,
      // Forward-looking hygiene, not a fix for a live bug: today the only
      // reader of `methodology` is approveData() in App.tsx, which always
      // creates a brand-new project, and reaching it again after a restore
      // needs dataApproved: false, which the normal flow never produces.
      // But OpenProjectSnapshot carries no methodology field, so a document
      // extracted-but-not-yet-attached in an interrupted or crashed session
      // would otherwise survive a restore unattached to any project. Nulling
      // it here also means the leak stays closed the moment
      // attachMethodology (added in this task, not yet wired to any UI
      // trigger) gains a caller.
      methodology: null,
    };
  }
}

export function useProjectStore() {
  const [state, dispatch] = useReducer(reducer, initialState);
  return {
    ...state,
    setActiveStep: (value: WorkflowStep) => dispatch({ type: "step", value }),
    setLanguage: (value: Language) => dispatch({ type: "language", value }),
    setBrief: (value: StudyBrief) => dispatch({ type: "brief", value }),
    setDataFile: (value: string | null) => dispatch({ type: "data", value }),
    approveDataStructure: () => dispatch({ type: "data_approved" }),
    setPlan: (value: AnalysisPlan | null) => dispatch({ type: "plan", value }),
    setPlanApproved: (value: boolean) => dispatch({ type: "plan_approved", value }),
    setResults: (value: AnalysisResult[]) => dispatch({ type: "results", value }),
    setMethodology: (value: MethodologyExtraction | null) => dispatch({ type: "methodology", value }),
    restoreProject: (value: OpenProjectSnapshot) => dispatch({ type: "restore", value }),
  };
}
