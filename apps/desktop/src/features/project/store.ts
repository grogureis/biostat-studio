import { useCallback, useState } from "react";

import type { AnalysisPlan, AnalysisResult, Language, StudyBrief } from "../../api/types";

export type WorkflowStep = "study" | "data" | "plan" | "run" | "results" | "report";

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

export function useProjectStore() {
  const [activeStep, setActiveStep] = useState<WorkflowStep>("study");
  const [language, setLanguageState] = useState<Language>("en");
  const [brief, setBrief] = useState<StudyBrief>(emptyBrief);
  const [dataFile, setDataFile] = useState<string | null>(null);
  const [plan, setPlan] = useState<AnalysisPlan | null>(null);
  const [results, setResults] = useState<AnalysisResult[]>([]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    setBrief((current) => ({ ...current, language: next }));
  }, []);

  return {
    activeStep,
    setActiveStep,
    language,
    setLanguage,
    brief,
    setBrief,
    dataFile,
    setDataFile,
    plan,
    setPlan,
    results,
    setResults,
  };
}
