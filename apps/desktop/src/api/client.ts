import type { AnalysisPlan, AnalysisResult, Language, StudyBrief } from "./types";

export interface AnalysisApi {
  selectDataFile(): Promise<string | null>;
  createPlan(brief: StudyBrief): Promise<AnalysisPlan>;
  runAnalysis(plan: AnalysisPlan): Promise<AnalysisResult[]>;
  cancelAnalysis(): Promise<void>;
  exportReport(results: AnalysisResult[], language: Language): Promise<string | null>;
}

type BiostatWindowBridge = Pick<Window["biostat"], "selectDataFile">;

const pendingWiring = (): never => {
  throw new Error("The local analysis service is not connected yet.");
};

/**
 * Renderer-safe boundary. Task 11 replaces the pending methods with authenticated
 * loopback requests; this task deliberately exposes no direct network or Node API.
 */
export function createAnalysisApi(bridge: BiostatWindowBridge): AnalysisApi {
  return Object.freeze({
    selectDataFile: () => bridge.selectDataFile(),
    createPlan: async () => pendingWiring(),
    runAnalysis: async () => pendingWiring(),
    cancelAnalysis: async () => pendingWiring(),
    exportReport: async () => pendingWiring(),
  });
}
