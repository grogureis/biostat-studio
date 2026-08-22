import type { AnalysisPlan, AnalysisResult, Language, StudyBrief } from "./types";

export interface AnalysisApi {
  selectDataFile(): Promise<string | null>;
  profileData?(): Promise<{ rows: number }>;
  approveDataStructure(brief: StudyBrief): Promise<void>;
  createPlan(brief: StudyBrief): Promise<AnalysisPlan>;
  approvePlan(plan: AnalysisPlan): Promise<void>;
  runAnalysis(plan: AnalysisPlan, onProgress?: (progress: JobProgress) => void): Promise<AnalysisResult[]>;
  cancelAnalysis(): Promise<void>;
  invalidateProject(): void;
  exportReport(results: AnalysisResult[], language: Language): Promise<string | null>;
}

export interface JobProgress {
  status: JobResponse["status"];
  progress: number;
  message: string | null;
  errorCode: string | null;
}

export class AnalysisApiError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "AnalysisApiError";
  }
}

type BiostatWindowBridge = Pick<
  Window["biostat"],
  "selectDataFile" | "selectReportDestination" | "requestApi"
>;

interface JobResponse {
  id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  result: { results?: AnalysisResult[]; warnings?: unknown[] } | null;
  progress: number;
  error_code: string | null;
  message: string | null;
}

const safeError = (): Error => new Error("The local analysis service could not complete this operation.");

function responseError(body: unknown): AnalysisApiError {
  if (body && typeof body === "object") {
    const envelope = body as { detail?: unknown; error?: { code?: unknown; message?: unknown } };
    if (
      envelope.error
      && typeof envelope.error.code === "string"
      && typeof envelope.error.message === "string"
    ) {
      return new AnalysisApiError(envelope.error.code, envelope.error.message);
    }
    if (typeof envelope.detail === "string") {
      return new AnalysisApiError(envelope.detail, "The local analysis service could not complete this operation.");
    }
  }
  return new AnalysisApiError("service_error", "The local analysis service could not complete this operation.");
}

/** Renderer-safe authenticated boundary for the local loopback service. */
export function createAnalysisApi(bridge: BiostatWindowBridge): AnalysisApi {
  let dataFile: string | null = null;
  let projectId: string | null = null;
  let activeJobId: string | null = null;
  let completedJobId: string | null = null;

  const send = async <T>(path: string, body?: unknown): Promise<T> => {
    const response = await bridge.requestApi({
      path,
      method: body === undefined ? "GET" : "POST",
      ...(body === undefined ? {} : { body }),
    });
    if (!response.ok) throw responseError(response.body);
    return response.body as T;
  };

  const requireProject = (): string => {
    if (!projectId) throw safeError();
    return projectId;
  };

  const invalidateProject = (): void => {
    const jobId = activeJobId;
    projectId = null;
    activeJobId = null;
    completedJobId = null;
    if (jobId) {
      void send<JobResponse>(`/v1/jobs/${jobId}/cancel`, {}).catch(() => undefined);
    }
  };

  return Object.freeze({
    selectDataFile: async () => {
      invalidateProject();
      dataFile = await bridge.selectDataFile();
      return dataFile;
    },
    profileData: async () => {
      if (!dataFile) throw safeError();
      return send<{ rows: number }>("/v1/data/profile", { source_path: dataFile });
    },
    approveDataStructure: async (brief: StudyBrief) => {
      if (!dataFile) throw safeError();
      const project = await send<{ id: string }>("/v1/projects", { source_path: dataFile, brief });
      projectId = project.id;
      await send<{ approved: boolean }>(`/v1/projects/${project.id}/data-approval`, {});
    },
    createPlan: async (_brief: StudyBrief) => {
      return send<AnalysisPlan>("/v1/plans", { project_id: requireProject() });
    },
    approvePlan: async (plan: AnalysisPlan) => {
      await send<{ approved: boolean }>("/v1/plans/approval", {
        project_id: requireProject(), revision: plan.revision, digest: plan.digest,
      });
    },
    runAnalysis: async (plan: AnalysisPlan, onProgress?: (progress: JobProgress) => void) => {
      const queued = await send<JobResponse>("/v1/jobs", {
        project_id: requireProject(),
        approved_plan_revision: plan.revision,
        approved_plan_digest: plan.digest,
      });
      activeJobId = queued.id;
      completedJobId = null;
      for (let attempts = 0; attempts < 120; attempts += 1) {
        const job = await send<JobResponse>(`/v1/jobs/${queued.id}`);
        onProgress?.({
          status: job.status,
          progress: job.progress ?? 0,
          message: job.message ?? null,
          errorCode: job.error_code ?? null,
        });
        if (job.status === "completed") {
          activeJobId = null;
          completedJobId = queued.id;
          return job.result?.results ?? [];
        }
        if (job.status === "failed" || job.status === "cancelled") {
          activeJobId = null;
          throw new AnalysisApiError(
            job.error_code ?? job.status,
            job.message ?? "The local analysis service could not complete this operation.",
          );
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 100));
      }
      activeJobId = null;
      throw new AnalysisApiError("analysis_timeout", "The local analysis service did not respond in time.");
    },
    cancelAnalysis: async () => {
      if (!activeJobId) return;
      const jobId = activeJobId;
      activeJobId = null;
      await send<JobResponse>(`/v1/jobs/${jobId}/cancel`, {});
    },
    invalidateProject,
    exportReport: async (_results: AnalysisResult[], language: Language) => {
      const destination = await bridge.selectReportDestination();
      if (!destination) return null;
      const jobId = completedJobId;
      if (!jobId) throw safeError();
      const exported = await send<{ saved: boolean; filename: string }>("/v1/reports", {
        project_id: requireProject(), job_id: jobId, language, destination,
      });
      return exported.saved ? exported.filename : null;
    },
  });
}
