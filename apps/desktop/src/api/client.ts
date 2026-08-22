import type { AnalysisPlan, AnalysisResult, DataProfile, Language, PowerRequest, PowerResponse, StudyBrief, VariableRole } from "./types";

export interface AnalysisApi {
  openProject?(): Promise<OpenProjectSnapshot | null>;
  selectDataFile(): Promise<string | null>;
  profileData?(): Promise<DataProfile>;
  approveDataStructure(brief: StudyBrief, roles?: VariableRole[]): Promise<void>;
  createPlan(brief: StudyBrief, methodOverrides?: Record<string, string>): Promise<AnalysisPlan>;
  computePower(request: PowerRequest): Promise<PowerResponse>;
  approvePlan(plan: AnalysisPlan): Promise<void>;
  runAnalysis(plan: AnalysisPlan, onProgress?: (progress: JobProgress) => void): Promise<AnalysisResult[]>;
  cancelAnalysis(): Promise<JobResponse | null>;
  invalidateProject(): void;
  exportReport(results: AnalysisResult[], language: Language): Promise<string | null>;
}

export interface OpenProjectSnapshot {
  id: string;
  brief: StudyBrief;
  roles: VariableRole[];
  plan: AnalysisPlan | null;
  approved_plan: boolean;
  completed_job_id: string | null;
  results: AnalysisResult[];
}

export interface JobProgress {
  status: JobResponse["status"];
  progress: number;
  message: string | null;
  errorCode: string | null;
}

export class AnalysisApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly diagnostics: ReadonlyArray<{ category: string }> = [],
  ) {
    super(message);
    this.name = "AnalysisApiError";
  }
}

type BiostatWindowBridge = Pick<
  Window["biostat"],
  "selectDataFile" | "selectProject" | "selectReportDestination" | "requestApi"
>;

export interface JobResponse {
  id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  result: { results?: AnalysisResult[]; warnings?: unknown[] } | null;
  progress: number;
  error_code: string | null;
  message: string | null;
  diagnostics?: Array<{ category?: unknown; code?: unknown }>;
}

const safeError = (): Error => new Error("The local analysis service could not complete this operation.");
const SAFE_DIAGNOSTIC_CATEGORIES = new Set(["separation", "convergence", "estimation", "numeric", "analysis", "library"]);

function safeDiagnostics(value: JobResponse["diagnostics"]): Array<{ category: string }> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => (
    item && typeof item.category === "string" && SAFE_DIAGNOSTIC_CATEGORIES.has(item.category)
      ? [{ category: item.category }]
      : []
  ));
}

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
  let dataFile: Awaited<ReturnType<BiostatWindowBridge["selectDataFile"]>> = null;
  let projectId: string | null = null;
  let activeJobId: string | null = null;
  let completedJobId: string | null = null;
  let activeTerminal: Promise<JobResponse> | null = null;

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
    completedJobId = null;
    if (jobId) {
      void send<JobResponse>(`/v1/jobs/${jobId}/cancel`, {}).catch(() => undefined);
    }
  };

  const waitForTerminal = (jobId: string, onProgress?: (progress: JobProgress) => void): Promise<JobResponse> => {
    return (async () => {
      let consecutiveFailures = 0;
      let delay = 100;
      const deadline = Date.now() + 90_000;
      while (Date.now() < deadline) {
        try {
          const job = await send<JobResponse>(`/v1/jobs/${jobId}`);
          consecutiveFailures = 0;
          onProgress?.({
            status: job.status,
            progress: job.progress ?? 0,
            message: job.message ?? null,
            errorCode: job.error_code ?? null,
          });
          if (["completed", "failed", "cancelled"].includes(job.status)) return job;
        } catch (error) {
          consecutiveFailures += 1;
          if (consecutiveFailures >= 5) throw error;
        }
        await new Promise<void>((resolve) => setTimeout(resolve, delay));
        delay = Math.min(delay * 2, 2_000);
      }
      throw new AnalysisApiError("analysis_timeout", "The local analysis service did not reach a terminal state in time.");
    })();
  };

  return Object.freeze({
    openProject: async () => {
      invalidateProject();
      const selection = await bridge.selectProject("open");
      if (!selection) return null;
      const restored = await send<OpenProjectSnapshot>("/v1/projects/open", {
        project_capability: selection.id,
      });
      projectId = restored.id;
      completedJobId = restored.completed_job_id;
      dataFile = null;
      return restored;
    },
    selectDataFile: async () => {
      invalidateProject();
      dataFile = await bridge.selectDataFile();
      return dataFile?.displayName ?? null;
    },
    profileData: async () => {
      if (!dataFile) throw safeError();
      return send<DataProfile>("/v1/data/profile", { source_capability: dataFile.profileCapability });
    },
    approveDataStructure: async (brief: StudyBrief, roles: VariableRole[] = []) => {
      if (!dataFile) throw safeError();
      const projectDirectory = await bridge.selectProject("create");
      if (!projectDirectory) throw new AnalysisApiError("project_selection_cancelled", "A project folder is required to continue.");
      const project = await send<{ id: string }>("/v1/projects", {
        source_capability: dataFile.importCapability,
        project_capability: projectDirectory.id,
        brief,
      });
      projectId = project.id;
      await send<{ approved: boolean }>(`/v1/projects/${project.id}/data-approval`, { roles });
    },
    createPlan: async (_brief: StudyBrief, methodOverrides: Record<string, string> = {}) => {
      return send<AnalysisPlan>("/v1/plans", {
        project_id: requireProject(),
        method_overrides: methodOverrides,
      });
    },
    computePower: async (request: PowerRequest) => {
      return send<PowerResponse>("/v1/power", request);
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
      activeTerminal = waitForTerminal(queued.id, onProgress);
      try {
        const job = await activeTerminal;
        if (job.status === "completed") {
          completedJobId = queued.id;
          return job.result?.results ?? [];
        }
        throw new AnalysisApiError(
          job.error_code ?? job.status,
          job.message ?? "The local analysis service could not complete this operation.",
          safeDiagnostics(job.diagnostics),
        );
      } finally {
        if (activeJobId === queued.id) activeJobId = null;
        activeTerminal = null;
      }
    },
    cancelAnalysis: async () => {
      if (!activeJobId) return null;
      const jobId = activeJobId;
      await send<JobResponse>(`/v1/jobs/${jobId}/cancel`, {});
      let terminal: JobResponse;
      if (activeTerminal) {
        terminal = await activeTerminal;
      } else {
        terminal = await waitForTerminal(jobId);
        if (!["completed", "failed", "cancelled"].includes(terminal.status)) {
          throw new AnalysisApiError("cancellation_failed", "Cancellation did not reach a terminal state.");
        }
      }
      if (terminal.status === "completed") completedJobId = jobId;
      if (activeJobId === jobId) activeJobId = null;
      return terminal;
    },
    invalidateProject,
    exportReport: async (_results: AnalysisResult[], language: Language) => {
      const destination = await bridge.selectReportDestination();
      if (!destination) return null;
      const jobId = completedJobId;
      if (!jobId) throw safeError();
      const exported = await send<{ saved: boolean; filename: string }>("/v1/reports", {
        project_id: requireProject(), job_id: jobId, language, destination_capability: destination.id,
      });
      return exported.saved ? exported.filename : null;
    },
  });
}
