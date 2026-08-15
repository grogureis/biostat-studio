import type { AnalysisPlan, AnalysisResult, Language, StudyBrief } from "./types";

export interface AnalysisApi {
  selectDataFile(): Promise<string | null>;
  profileData?(): Promise<{ rows: number }>;
  createPlan(brief: StudyBrief): Promise<AnalysisPlan>;
  runAnalysis(plan: AnalysisPlan): Promise<AnalysisResult[]>;
  cancelAnalysis(): Promise<void>;
  exportReport(results: AnalysisResult[], language: Language): Promise<string | null>;
}

type BiostatWindowBridge = Pick<
  Window["biostat"],
  "selectDataFile" | "selectReportDestination" | "getApiSession"
>;
type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface JobResponse {
  id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  result: { results?: AnalysisResult[]; warnings?: unknown[] } | null;
}

const safeError = (): Error => new Error("The local analysis service could not complete this operation.");

/** Renderer-safe authenticated boundary for the local loopback service. */
export function createAnalysisApi(bridge: BiostatWindowBridge, request: Fetch = fetch): AnalysisApi {
  let dataFile: string | null = null;
  let projectId: string | null = null;
  let activeJobId: string | null = null;

  const send = async <T>(path: string, body?: unknown): Promise<T> => {
    const session = await bridge.getApiSession();
    const response = await request(`${session.apiBase}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { Authorization: `Bearer ${session.token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw safeError();
    return response.json() as Promise<T>;
  };

  const requireProject = (): string => {
    if (!projectId) throw safeError();
    return projectId;
  };

  return Object.freeze({
    selectDataFile: async () => {
      dataFile = await bridge.selectDataFile();
      projectId = null;
      activeJobId = null;
      return dataFile;
    },
    profileData: async () => {
      if (!dataFile) throw safeError();
      return send<{ rows: number }>("/v1/data/profile", { source_path: dataFile });
    },
    createPlan: async (brief: StudyBrief) => {
      if (!dataFile) throw safeError();
      const project = await send<{ id: string }>("/v1/projects", { source_path: dataFile, brief });
      projectId = project.id;
      return send<AnalysisPlan>("/v1/plans", { project_id: project.id });
    },
    runAnalysis: async (plan: AnalysisPlan) => {
      const queued = await send<JobResponse>("/v1/jobs", {
        project_id: requireProject(),
        approved_plan_version: plan.version,
      });
      activeJobId = queued.id;
      for (let attempts = 0; attempts < 120; attempts += 1) {
        const job = await send<JobResponse>(`/v1/jobs/${queued.id}`);
        if (job.status === "completed") {
          return job.result?.results ?? [];
        }
        if (job.status === "failed" || job.status === "cancelled") {
          activeJobId = null;
          throw safeError();
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 100));
      }
      activeJobId = null;
      throw safeError();
    },
    cancelAnalysis: async () => {
      if (!activeJobId) return;
      const jobId = activeJobId;
      activeJobId = null;
      await send<JobResponse>(`/v1/jobs/${jobId}/cancel`, {});
    },
    exportReport: async (_results: AnalysisResult[], language: Language) => {
      const destination = await bridge.selectReportDestination();
      if (!destination) return null;
      const jobId = activeJobId;
      if (!jobId) throw safeError();
      const exported = await send<{ saved: boolean; filename: string }>("/v1/reports", {
        project_id: requireProject(), job_id: jobId, language, destination,
      });
      return exported.saved ? exported.filename : null;
    },
  });
}
