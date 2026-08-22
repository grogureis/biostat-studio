import { describe, expect, it, vi } from "vitest";

import { createAnalysisApi } from "./client";
import type { AnalysisPlan, StudyBrief } from "./types";

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
      selectDataFile: vi.fn().mockResolvedValue("/private/study.xlsx"),
      selectReportDestination: vi.fn().mockResolvedValue("/private/Results.docx"),
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
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ progress: 45, message: "Running approved methods." }));
  });

  it("cancels the active job and never returns partial results", async () => {
    const requestApi = vi.fn().mockResolvedValue({ ok: true, status: 200, body: { id: "job-1", status: "cancelled", result: null } });
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectReportDestination: vi.fn(),
      requestApi,
    });

    await api.cancelAnalysis();
    expect(requestApi).not.toHaveBeenCalled();
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
      selectDataFile: vi.fn().mockResolvedValue("/private/study.xlsx"),
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
});
