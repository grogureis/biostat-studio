import { describe, expect, it, vi } from "vitest";

import { AnalysisApiError, createAnalysisApi } from "./client";
import type { AnalysisPlan, StudyBrief } from "./types";

const extraction = {
  source_sha256: "a".repeat(64),
  source_format: "docx",
  char_count: 10,
  truncated: false,
  warnings: [] as string[],
  brief: {
    title: null, question: null, hypothesis: null, design: null,
    outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [],
  },
};

const brief: StudyBrief = {
  title: "Comparison",
  question: "Does treatment change the outcome?",
  hypothesis: "Treatment is associated with a difference.",
  design: "cohort",
  outcome_variables: ["outcome"],
  exposure_variables: ["group"],
};

const plan: AnalysisPlan = {
  version: 1,
  revision: "11111111-1111-4111-8111-111111111111",
  digest: "a".repeat(64),
  items: [],
  blocking_errors: [],
  warnings: [],
};

describe("authenticated loopback API client", () => {
  it("opens only a native-selected project capability and restores its completed job", async () => {
    const restored = { id: "project-1", brief, roles: [], plan, approved_plan: true, completed_job_id: "job-1", results: [] };
    const requestApi = vi.fn().mockResolvedValue({ ok: true, status: 200, body: restored });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "open-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(), requestApi,
    });

    await expect(api.openProject!()).resolves.toEqual(restored);
    expect(requestApi).toHaveBeenCalledWith({
      path: "/v1/projects/open", method: "POST", body: { project_capability: "open-cap" },
    });
  });
  it("creates a project, plans, runs the approved version, and exports only after completion", async () => {
    const requestApi = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "project-1", profile: { rows: 12 } } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { approved: true } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: plan })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { approved: true, revision: plan.revision, digest: plan.digest } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "job-1", status: "queued", result: null } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "job-1", status: "running", progress: 45, message: "Running approved methods.", error_code: null, result: null } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "job-1", status: "completed", progress: 100, message: "Publishing verified results.", error_code: null, result: { results: [], warnings: [] } } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { saved: true, filename: "Results.docx" } });
    const bridge = {
      selectDataFile: vi.fn().mockResolvedValue({ displayName: "study.xlsx", profileCapability: "profile-cap", importCapability: "import-cap" }),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "create-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn().mockResolvedValue({ id: "report-cap", displayName: "Results.docx" }),
      requestApi,
    };
    const api = createAnalysisApi(bridge);
    const progress = vi.fn();

    await api.selectDataFile();
    await expect(api.approveDataStructure(brief)).resolves.toBeUndefined();
    await expect(api.createPlan(brief)).resolves.toEqual(plan);
    await expect(api.approvePlan(plan)).resolves.toBeUndefined();
    await expect(api.runAnalysis(plan, progress)).resolves.toEqual([]);
    await expect(api.exportReport([], "en")).resolves.toBe("Results.docx");

    expect(requestApi.mock.calls.map(([request]) => request.path)).toEqual([
      "/v1/projects", "/v1/projects/project-1/data-approval", "/v1/plans", "/v1/plans/approval",
      "/v1/jobs", "/v1/jobs/job-1", "/v1/jobs/job-1", "/v1/reports",
    ]);
    expect(requestApi.mock.calls[4][0]).toMatchObject({
      body: { project_id: "project-1", approved_plan_revision: plan.revision, approved_plan_digest: plan.digest },
    });
    expect(requestApi.mock.calls[0][0].body).toMatchObject({ source_capability: "import-cap", project_capability: "create-cap" });
    expect(bridge.selectProject).toHaveBeenCalledWith("create");
    expect(JSON.stringify(requestApi.mock.calls)).not.toContain("/private/study.xlsx");
    expect(requestApi.mock.calls[7][0].body).toMatchObject({ destination_capability: "report-cap" });
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ progress: 45, message: "Running approved methods." }));
  });

  it("prepares the project before data approval so variable proposals are reviewable", async () => {
    const requestApi = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "project-1", profile: { rows: 12 } } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { proposals: [], conflicts: [] } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { approved: true } });
    const api = createAnalysisApi({
      selectDataFile: vi.fn().mockResolvedValue({ displayName: "study.xlsx", profileCapability: "profile-cap", importCapability: "import-cap" }),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "create-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    await api.selectDataFile();
    const preparing = api as typeof api & { prepareDataStructure(brief: StudyBrief): Promise<{ proposals: unknown[]; conflicts: unknown[] }> };
    await expect(preparing.prepareDataStructure(brief)).resolves.toEqual({ proposals: [], conflicts: [] });
    await api.approveDataStructure(brief, []);

    expect(requestApi.mock.calls.map(([request]) => request.path)).toEqual([
      "/v1/projects",
      "/v1/projects/project-1/variable-proposals",
      "/v1/projects/project-1/data-approval",
    ]);
    expect(requestApi.mock.calls[0][0].body).toMatchObject({
      source_capability: "import-cap",
      project_capability: "create-cap",
    });
  });

  it("computes power statelessly and sends plan method overrides", async () => {
    const requestApi = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, body: { analysis: "two_sample_t", per_group_rounded: 64 } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { id: "project-1", profile: { rows: 12 } } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: { approved: true } })
      .mockResolvedValueOnce({ ok: true, status: 200, body: plan });
    const bridge = {
      selectDataFile: vi.fn().mockResolvedValue({ displayName: "study.xlsx", profileCapability: "profile-cap", importCapability: "import-cap" }),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "create-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(),
      requestApi,
    };
    const api = createAnalysisApi(bridge);

    await expect(api.computePower({
      analysis: "two_sample_t", solve_for: "sample_size", alpha: 0.05, power: 0.8, effect_size: 0.5,
    })).resolves.toMatchObject({ per_group_rounded: 64 });
    expect(requestApi.mock.calls[0][0]).toMatchObject({
      path: "/v1/power",
      method: "POST",
      body: { analysis: "two_sample_t", solve_for: "sample_size" },
    });

    await api.selectDataFile();
    await api.approveDataStructure(brief);
    await api.createPlan(brief, { primary_outcome: "mann_whitney_u" });
    expect(requestApi.mock.calls[3][0]).toMatchObject({
      path: "/v1/plans",
      body: { project_id: "project-1", method_overrides: { primary_outcome: "mann_whitney_u" } },
    });
  });

  it("cancels the active job and never returns partial results", async () => {
    const requestApi = vi.fn().mockResolvedValue({ ok: true, status: 200, body: { id: "job-1", status: "cancelled", result: null } });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "create-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    await api.cancelAnalysis();
    expect(requestApi).not.toHaveBeenCalled();
  });

  it("keeps authoritative job ownership while cancelling until the server is terminal", async () => {
    let releaseRunning!: (value: { ok: boolean; status: number; body: unknown }) => void;
    const runningPoll = new Promise<{ ok: boolean; status: number; body: unknown }>((resolve) => { releaseRunning = resolve; });
    let polls = 0;
    const requestApi = vi.fn((request: { path: string }) => {
      if (request.path === "/v1/projects/open") return Promise.resolve({ ok: true, status: 200, body: { id: "project-1", brief, roles: [], plan, approved_plan: true, completed_job_id: null, results: [] } });
      if (request.path === "/v1/jobs") return Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "queued", result: null } });
      if (request.path === "/v1/jobs/job-1/cancel") return Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "cancelling", result: null } });
      polls += 1;
      return polls === 1 ? runningPoll : Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "cancelled", progress: 100, result: null } });
    });
    const api = createAnalysisApi({ selectDataFile: vi.fn(), selectMethodologyDocument: vi.fn(), selectProject: vi.fn().mockResolvedValue({ id: "open-cap", displayName: "study.biostat" }), selectReportDestination: vi.fn(), requestApi });

    await api.openProject!();
    const run = api.runAnalysis(plan);
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1" })));
    const cancelling = api.cancelAnalysis();
    let cancelResolved = false;
    void cancelling.then(() => { cancelResolved = true; });
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1/cancel" })));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(cancelResolved).toBe(false);
    releaseRunning({ ok: true, status: 200, body: { id: "job-1", status: "cancelling", progress: 45, result: null } });

    await expect(cancelling).resolves.toMatchObject({ id: "job-1", status: "cancelled" });
    await expect(run).rejects.toMatchObject({ code: "cancelled" });
    expect(requestApi.mock.calls.map(([request]) => request.path)).toContain("/v1/jobs/job-1/cancel");
  });

  it("returns the authoritative completed job when completion wins cancellation", async () => {
    let releasePoll!: (value: { ok: boolean; status: number; body: unknown }) => void;
    const pendingPoll = new Promise<{ ok: boolean; status: number; body: unknown }>((resolve) => {
      releasePoll = resolve;
    });
    const requestApi = vi.fn((request: { path: string }) => {
      if (request.path === "/v1/projects/open") return Promise.resolve({ ok: true, status: 200, body: { id: "project-1", brief, roles: [], plan, approved_plan: true, completed_job_id: null, results: [] } });
      if (request.path === "/v1/jobs") return Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "queued", result: null } });
      if (request.path === "/v1/jobs/job-1/cancel") return Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "cancelling", result: null } });
      return pendingPoll;
    });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "open-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(),
      requestApi,
    });
    await api.openProject!();
    const running = api.runAnalysis(plan);
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1" })));

    const cancelling = api.cancelAnalysis();
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1/cancel" })));
    releasePoll({
      ok: true,
      status: 200,
      body: { id: "job-1", status: "completed", progress: 100, message: "Published.", error_code: null, result: { results: [], warnings: [] } },
    });

    await expect(cancelling).resolves.toMatchObject({ id: "job-1", status: "completed" });
    await expect(running).resolves.toEqual([]);
  });

  it("backs off successful non-terminal polling instead of polling every 100 ms", async () => {
    vi.useFakeTimers();
    try {
      let polls = 0;
      const requestApi = vi.fn((request: { path: string }) => {
        if (request.path === "/v1/projects/open") return Promise.resolve({ ok: true, status: 200, body: { id: "project-1", brief, roles: [], plan, approved_plan: true, completed_job_id: null, results: [] } });
        if (request.path === "/v1/jobs") return Promise.resolve({ ok: true, status: 200, body: { id: "job-1", status: "queued", result: null } });
        polls += 1;
        return Promise.resolve({
          ok: true,
          status: 200,
          body: polls < 3
            ? { id: "job-1", status: "running", progress: polls * 10, result: null }
            : { id: "job-1", status: "completed", progress: 100, error_code: null, result: { results: [], warnings: [] } },
        });
      });
      const api = createAnalysisApi({
        selectDataFile: vi.fn(),
        selectMethodologyDocument: vi.fn(),
        selectProject: vi.fn().mockResolvedValue({ id: "open-cap", displayName: "study.biostat" }),
        selectReportDestination: vi.fn(),
        requestApi,
      });
      await api.openProject!();
      const running = api.runAnalysis(plan);
      await vi.advanceTimersByTimeAsync(0);
      expect(polls).toBe(1);

      await vi.advanceTimersByTimeAsync(100);
      expect(polls).toBe(2);
      await vi.advanceTimersByTimeAsync(199);
      expect(polls).toBe(2);
      await vi.advanceTimersByTimeAsync(1);

      await expect(running).resolves.toEqual([]);
      expect(polls).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("cooperatively cancels an active job when project inputs are invalidated", async () => {
    let releasePoll!: (response: { ok: boolean; status: number; body: unknown }) => void;
    const pendingPoll = new Promise<{ ok: boolean; status: number; body: unknown }>((resolve) => {
      releasePoll = resolve;
    });
    const requestApi = vi.fn(async (request: { path: string }) => {
      if (request.path === "/v1/projects") return { ok: true, status: 200, body: { id: "project-1" } };
      if (request.path === "/v1/projects/project-1/data-approval") return { ok: true, status: 200, body: { approved: true } };
      if (request.path === "/v1/jobs") return { ok: true, status: 200, body: { id: "job-1", status: "queued", result: null } };
      if (request.path === "/v1/jobs/job-1/cancel") return { ok: true, status: 200, body: { id: "job-1", status: "cancelling", result: null } };
      return pendingPoll;
    });
    const api = createAnalysisApi({
      selectDataFile: vi.fn().mockResolvedValue({ displayName: "study.xlsx", profileCapability: "profile-cap", importCapability: "import-cap" }),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn().mockResolvedValue({ id: "create-cap", displayName: "study.biostat" }),
      selectReportDestination: vi.fn(),
      requestApi,
    });
    await api.selectDataFile();
    await api.approveDataStructure(brief);
    const running = api.runAnalysis(plan);
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1" })));

    api.invalidateProject();
    await vi.waitFor(() => expect(requestApi).toHaveBeenCalledWith(expect.objectContaining({ path: "/v1/jobs/job-1/cancel" })));
    releasePoll({ ok: true, status: 200, body: { id: "job-1", status: "cancelled", progress: 100, message: null, error_code: null, result: null } });
    await expect(running).rejects.toMatchObject({ code: "cancelled" });
  });

  it("extracts methodology using the capability issued by the picker, without exposing a path", async () => {
    const sent: Array<{ path: string; body: unknown }> = [];
    const requestApi = vi.fn(async (request: { path: string; body?: unknown }) => {
      sent.push({ path: request.path, body: request.body });
      return { ok: true, status: 200, body: extraction };
    });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn().mockResolvedValue({ id: "cap-1", displayName: "protokol.docx" }),
      selectProject: vi.fn(),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    const name = await api.selectMethodologyDocument!();
    const result = await api.extractMethodology!();

    expect(name).toBe("protokol.docx");
    expect(JSON.stringify(sent)).not.toMatch(/[\\/].*protokol/);
    expect(sent.at(-1)?.path).toBe("/v1/methodology/extract");
    expect(sent.at(-1)?.body).toEqual({ source_capability: "cap-1" });
    expect(result).toEqual(extraction);
    expect(result.brief.warnings).toEqual([]);
  });

  it("treats the methodology capability as single-use and rejects a second extraction locally", async () => {
    const requestApi = vi.fn().mockResolvedValue({ ok: true, status: 200, body: extraction });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn().mockResolvedValue({ id: "cap-1", displayName: "protokol.docx" }),
      selectProject: vi.fn(),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    await api.selectMethodologyDocument!();
    await expect(api.extractMethodology!()).resolves.toEqual(extraction);

    const rejected = api.extractMethodology!();
    await expect(rejected).rejects.toBeInstanceOf(AnalysisApiError);
    // Pin the code, not just the type: the renderer keys its error copy off
    // this string, so a rename here must break a test.
    await expect(rejected).rejects.toMatchObject({ code: "methodology_document_not_selected" });
    expect(requestApi).toHaveBeenCalledTimes(1);
  });

  it("refuses to extract before a methodology document has ever been selected", async () => {
    const requestApi = vi.fn();
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectMethodologyDocument: vi.fn(),
      selectProject: vi.fn(),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    const rejected = api.extractMethodology!();
    await expect(rejected).rejects.toBeInstanceOf(AnalysisApiError);
    await expect(rejected).rejects.toMatchObject({ code: "methodology_document_not_selected" });
    expect(requestApi).not.toHaveBeenCalled();
  });
});
