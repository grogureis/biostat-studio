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

const plan: AnalysisPlan = { version: 1, items: [], blocking_errors: [], warnings: [] };

describe("authenticated loopback API client", () => {
  it("creates a project, plans, runs the approved version, and exports only after completion", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "project-1", profile: { rows: 12 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(plan), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "job-1", status: "queued", result: null }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "job-1", status: "completed", result: { results: [], warnings: [] } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ saved: true, filename: "Results.docx" }), { status: 200 }));
    const bridge = {
      selectDataFile: vi.fn().mockResolvedValue("/private/study.xlsx"),
      selectReportDestination: vi.fn().mockResolvedValue("/private/Results.docx"),
      getApiSession: vi.fn().mockResolvedValue({ apiBase: "http://127.0.0.1:4040", token: "token" }),
    };
    const api = createAnalysisApi(bridge, request);

    await api.selectDataFile();
    await expect(api.createPlan(brief)).resolves.toEqual(plan);
    await expect(api.runAnalysis(plan)).resolves.toEqual([]);
    await expect(api.exportReport([], "en")).resolves.toBe("Results.docx");

    expect(request.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:4040/v1/projects",
      "http://127.0.0.1:4040/v1/plans",
      "http://127.0.0.1:4040/v1/jobs",
      "http://127.0.0.1:4040/v1/jobs/job-1",
      "http://127.0.0.1:4040/v1/reports",
    ]);
    expect(request.mock.calls[2][1]).toMatchObject({ body: JSON.stringify({ project_id: "project-1", approved_plan_version: 1 }) });
    expect(request.mock.calls.every(([, options]) => options.headers.Authorization === "Bearer token")).toBe(true);
  });

  it("cancels the active job and never returns partial results", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "job-1", status: "cancelled", result: null }), { status: 200 }));
    const api = createAnalysisApi({
      selectDataFile: vi.fn(),
      selectReportDestination: vi.fn(),
      getApiSession: vi.fn().mockResolvedValue({ apiBase: "http://127.0.0.1:4040", token: "token" }),
    }, request);

    await api.cancelAnalysis();
    expect(request).not.toHaveBeenCalled();
  });
});
