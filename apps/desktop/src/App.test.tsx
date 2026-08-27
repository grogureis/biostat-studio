// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { AnalysisApiError, type AnalysisApi } from "./api/client";
import type { AnalysisPlan, AnalysisResult } from "./api/types";

const plan: AnalysisPlan = {
  version: 1,
  revision: "11111111-1111-4111-8111-111111111111",
  digest: "a".repeat(64),
  items: [
    {
      id: "primary",
      estimand: "Mean difference in systolic blood pressure",
      method: "Welch independent-samples t-test",
      rationale: "Two independent groups with a continuous outcome.",
      required_variables: ["treatment", "systolic_bp"],
      assumptions: ["Independent observations", "Finite variance"],
      robust_alternative: "Mann–Whitney U test",
      multiplicity_strategy: null,
      outputs: ["Mean difference", "95% confidence interval", "Hedges' g"],
      blocking_errors: [],
      warnings: ["Review the small number of missing outcome values."],
    },
  ],
  blocking_errors: [],
  warnings: ["Review the small number of missing outcome values."],
};

const result: AnalysisResult = {
  id: "primary",
  method: "welch_t_test",
  n: 12,
  estimate: -4.2,
  p_value: 0.032,
  confidence_interval: { level: 0.95, lower: -8.01, upper: -0.39 },
  effect_size: { name: "Hedges' g", value: -0.71 },
  provenance: {
    data_fingerprint: "e5f89c9b7a14",
    plan_version: 1,
    exclusions: ["1 row with missing systolic_bp"],
    transformations: [],
    random_seed: null,
    library_versions: { scipy: "1.16.1" },
  },
  diagnostics: {},
  exclusions: ["1 row with missing systolic_bp"],
  warnings: [],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

const powerResponse = {
  analysis: "two_sample_t" as const,
  solve_for: "sample_size" as const,
  inputs: { alpha: 0.05, standardized_effect_size: 0.5, target_power: 0.8 },
  sample_size_unit: "per_group" as const,
  power: null,
  sample_size: 63.765611775409695,
  per_group_rounded: 64,
  total_rounded: 128,
  achieved_power: 0.8014595500498423,
  method: "statsmodels_power_solver:cohen_d",
  library_versions: { python: "3.12.14" },
};

function fakeApi(overrides: Partial<AnalysisApi> = {}): AnalysisApi {
  return {
    selectDataFile: vi.fn().mockResolvedValue("/Users/research/core-study.xlsx"),
    computePower: vi.fn().mockResolvedValue(powerResponse),
    profileData: vi.fn().mockResolvedValue({ rows: 12, columns: 2, missing_cells: 0, sheets: ["Sheet1"], selected_sheet: "Sheet1", variables: {
      treatment: { display_name: "Treatment", kind: "binary", non_missing: 12, missing: 0, unique_values: 2 },
      systolic_bp: { display_name: "Systolic bp", kind: "continuous", non_missing: 12, missing: 0, unique_values: 12 },
    }, warnings: [] }),
    approveDataStructure: vi.fn().mockResolvedValue(undefined),
    createPlan: vi.fn().mockResolvedValue(plan),
    approvePlan: vi.fn().mockResolvedValue(undefined),
    runAnalysis: vi.fn().mockResolvedValue([result]),
    cancelAnalysis: vi.fn().mockResolvedValue(null),
    invalidateProject: vi.fn(),
    exportReport: vi.fn().mockResolvedValue("/Users/research/Results.docx"),
    ...overrides,
  };
}

async function openApprovedDataPlan(
  user: ReturnType<typeof userEvent.setup>,
  language: "en" | "tr" = "en",
) {
  await user.click(screen.getByRole("button", { name: language === "en" ? "Data & variables" : "Veri ve değişkenler" }));
  await user.click(screen.getByRole("button", { name: language === "en" ? "Import Excel" : "Excel içe aktar" }));
  await user.click(await screen.findByRole("button", { name: language === "en" ? "Accept remaining clear variables" : "Kalan uygun değişkenleri kabul et" }));
  await user.click(await screen.findByRole("button", { name: language === "en" ? "Approve data structure" : "Veri yapısını onayla" }));
  await waitFor(() => expect(screen.getByRole("button", { name: language === "en" ? "Data structure approved" : "Veri yapısı onaylandı" })).toBeDisabled());
  await user.click(screen.getByRole("button", { name: language === "en" ? "Analysis plan" : "Analiz planı" }));
}

afterEach(() => {
  cleanup();
});

describe("Clinical Calm workflow", () => {
  it("shows only an allowlisted safe diagnostic category for a failed analysis", async () => {
    const api = fakeApi({
      runAnalysis: vi.fn().mockRejectedValue(new AnalysisApiError(
        "analysis_execution_error",
        "Analysis could not be completed.",
        [{ category: "separation" }],
      )),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Safe diagnostic category: separation.");
    expect(screen.queryByRole("heading", { name: "Results" })).not.toBeInTheDocument();
  });
  it("presents seven semantic stages and requires plan approval before analysis", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi()} />);

    expect(screen.getByRole("navigation", { name: "Analysis workflow" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^(Study brief|Data & variables|Analysis plan|Run & diagnose|Results review|Word report|Power & sample size)$/ })).toHaveLength(7);
    expect(screen.getByText("Offline · data stays on this Mac")).toBeInTheDocument();

    await openApprovedDataPlan(user);
    expect(screen.getByRole("heading", { name: "Analysis plan" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Documented alternative (not automatically executed)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeEnabled();
  });

  it("announces progress and supports cancellation without presenting partial results", async () => {
    const pending = deferred<AnalysisResult[]>();
    const api = fakeApi({
      runAnalysis: vi.fn((_plan, onProgress) => {
        onProgress?.({ status: "running", progress: 35, message: "Running approved methods.", errorCode: null });
        return pending.promise;
      }),
      cancelAnalysis: vi.fn().mockResolvedValue({ id: "job-1", status: "cancelled", result: null, progress: 100, error_code: null, message: null }),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(screen.getByRole("heading", { name: "Run & diagnose" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Running approved methods.");
    expect(screen.getByRole("progressbar", { name: "Analysis progress" })).toHaveAttribute("aria-valuenow", "35");

    await user.click(screen.getByRole("button", { name: "Cancel analysis" }));
    expect(api.cancelAnalysis).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent("Analysis cancelled. No partial results were accepted.");
    expect(screen.queryByRole("heading", { name: "Results" })).not.toBeInTheDocument();
  });

  it("shows completed results when completion wins the cancellation race", async () => {
    const pending = deferred<AnalysisResult[]>();
    const api = fakeApi({
      runAnalysis: vi.fn(() => pending.promise),
      cancelAnalysis: vi.fn().mockResolvedValue({
        id: "job-1",
        status: "completed",
        result: { results: [result], warnings: [] },
        progress: 100,
        error_code: null,
        message: "Published.",
      }),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    await user.click(screen.getByRole("button", { name: "Cancel analysis" }));

    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(screen.queryByText("Analysis cancelled. No partial results were accepted.")).not.toBeInTheDocument();
  });

  it("shows actionable non-color-only errors and retries the failed analysis", async () => {
    const api = fakeApi({
      runAnalysis: vi
        .fn()
        .mockRejectedValueOnce(new Error("service unavailable"))
        .mockResolvedValueOnce([result]),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Analysis could not be completed");
    expect(alert.querySelector("[aria-hidden='true']")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "Retry analysis" }));
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(api.runAnalysis).toHaveBeenCalledTimes(2);
  });

  it("switches all application copy to Turkish while preserving the same plan", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Interface language" }), "tr");

    expect(document.documentElement.lang).toBe("tr");
    expect(screen.getByRole("navigation", { name: "Analiz iş akışı" })).toBeInTheDocument();
    expect(screen.getByText("Çevrimdışı · veriler bu Mac'te kalır")).toBeInTheDocument();
    await openApprovedDataPlan(user, "tr");
    expect(await screen.findByText("Welch independent-samples t-test")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Belgelenmiş alternatif (otomatik yürütülmez)" })).toBeInTheDocument();
    expect(api.createPlan).toHaveBeenCalledWith(expect.objectContaining({ language: "en" }), {});
    expect(api.invalidateProject).not.toHaveBeenCalled();

    await user.click(screen.getByRole("checkbox", { name: "Bu planı onayla" }));
    await user.click(screen.getByRole("button", { name: "Analizi çalıştır" }));
    expect(await screen.findByRole("heading", { name: "Sonuçlar" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Word raporu" }));
    const reportLanguage = screen.getByRole("combobox", { name: "Rapor dili" });
    expect(reportLanguage).toHaveTextContent("İngilizce");
    expect(reportLanguage).toHaveTextContent("Türkçe");
  });

  it("exports the Word report through an explicit accessible action", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    await screen.findByRole("heading", { name: "Results" });
    await user.click(screen.getByRole("button", { name: "Word report" }));
    await user.click(screen.getByRole("button", { name: "Export Word report" }));

    expect(api.exportReport).toHaveBeenCalledWith([result], "en");
    expect(await screen.findByRole("status")).toHaveTextContent("Word report saved");
  });

  it("uses an accessible skip link and native labelled study controls", () => {
    render(<App api={fakeApi()} />);

    expect(screen.getByRole("link", { name: "Skip to active task" })).toHaveAttribute("href", "#workspace");
    expect(screen.getByRole("textbox", { name: "Research question" })).toBeRequired();
    expect(screen.getByRole("textbox", { name: "Hypothesis" })).toBeRequired();
    expect(screen.getByRole("combobox", { name: "Study design" })).toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: "Tab" });
    expect(screen.getByRole("link", { name: "Skip to active task" })).toBeInTheDocument();
  });

  it("retries plan generation rather than incorrectly running analysis after a planning failure", async () => {
    const api = fakeApi({
      createPlan: vi.fn().mockRejectedValueOnce(new Error("service unavailable")).mockResolvedValueOnce(plan),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis plan could not be completed");
    expect(api.runAnalysis).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Retry plan generation" }));
    expect(api.createPlan).toHaveBeenCalledTimes(2);
    expect(api.runAnalysis).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Run analysis" })).toBeDisabled();
  });

  it("presents result warnings with text and an icon, and includes them in the inspector", async () => {
    const warnedResult = { ...result, warnings: ["One influential observation merits review."] };
    const api = fakeApi({ runAnalysis: vi.fn().mockResolvedValue([warnedResult]) });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    const warning = await screen.findByRole("note", { name: "Warning requiring review" });
    expect(warning).toHaveTextContent("This result includes a warning that should be reviewed before release.");
    expect(warning).toHaveTextContent("One influential observation merits review.");
    expect(warning.querySelector("[aria-hidden='true']")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Warnings to review" })).toBeInTheDocument();
  });

  it("keeps visible UI copy Turkish in the run, report, inspector, and error states", async () => {
    const api = fakeApi({ createPlan: vi.fn().mockRejectedValueOnce(new Error("service unavailable")).mockResolvedValueOnce(plan) });
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Interface language" }), "tr");
    expect(screen.getByText("YÖNTEM NOTU")).toBeInTheDocument();
    expect(screen.getByText("Yerel kullanım")).toBeInTheDocument();
    await openApprovedDataPlan(user, "tr");
    expect(await screen.findByRole("alert")).toHaveTextContent("Analiz planı tamamlanamadı");
    expect(screen.getByRole("button", { name: "Plan oluşturmayı yeniden dene" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Plan oluşturmayı yeniden dene" }));
    await user.click(screen.getByRole("checkbox", { name: "Bu planı onayla" }));
    await user.click(screen.getByRole("button", { name: "Analizi çalıştır" }));
    await screen.findByRole("heading", { name: "Sonuçlar" });
    await user.click(screen.getByRole("button", { name: "Word raporu" }));
    expect(screen.getByText("Sonuçlar bölümü")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Word raporunu dışa aktar" })).toBeEnabled();
  });

  it("gates results and report export until validated results exist, then retries an export failure", async () => {
    const api = fakeApi({
      exportReport: vi.fn().mockRejectedValueOnce(new Error("write failed")).mockResolvedValueOnce("/Users/research/Results.docx"),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    expect(screen.getByRole("button", { name: "Results review" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Word report" })).toBeDisabled();

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    await screen.findByRole("heading", { name: "Results" });
    await user.click(screen.getByRole("button", { name: "Word report" }));
    await user.click(screen.getByRole("button", { name: "Export Word report" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Word report could not be completed");
    await user.click(screen.getByRole("button", { name: "Retry Word export" }));
    expect(api.exportReport).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("status")).toHaveTextContent("Word report saved");
  });

  it("regenerates the plan with the documented alternative and clears approval", async () => {
    const swapped: AnalysisPlan = {
      ...plan,
      items: [{
        ...plan.items[0],
        method: "Mann–Whitney U test",
        robust_alternative: "Welch independent-samples t-test",
      }],
    };
    const api = fakeApi({
      createPlan: vi.fn().mockResolvedValueOnce(plan).mockResolvedValueOnce(swapped),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Use this alternative (regenerate plan)" }));

    expect(await screen.findByRole("heading", { name: "Mann–Whitney U test" })).toBeInTheDocument();
    expect(api.createPlan).toHaveBeenLastCalledWith(
      expect.objectContaining({ language: "en" }),
      { primary: "Mann–Whitney U test" },
    );
    expect(screen.getByRole("checkbox", { name: "Approve this plan" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  });

  it("computes power and sample size without any project", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Power & sample size" }));
    expect(screen.getByRole("heading", { name: "Power & sample size" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Compute" }));

    expect(api.computePower).toHaveBeenCalledWith(expect.objectContaining({
      analysis: "two_sample_t",
      solve_for: "sample_size",
      alpha: 0.05,
      power: 0.8,
      effect_size: 0.5,
    }));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("64");
    expect(status).toHaveTextContent("128");
    expect(api.invalidateProject).not.toHaveBeenCalled();
  });

  it("localizes the power planner and shows a safe failure message", async () => {
    const api = fakeApi({
      computePower: vi.fn().mockRejectedValue(new AnalysisApiError("invalid_alpha", "invalid")),
    });
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Interface language" }), "tr");
    await user.click(screen.getByRole("button", { name: "Güç ve örneklem" }));
    expect(screen.getByRole("heading", { name: "Güç ve örneklem büyüklüğü" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hesapla" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Hesaplama tamamlanamadı");
  });

  it("handles a file-picker exception without exposing a path or crashing", async () => {
    const api = fakeApi({ selectDataFile: vi.fn().mockRejectedValue(new Error("picker unavailable")) });
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Data & variables" }));
    await user.click(screen.getByRole("button", { name: "Import Excel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The workbook picker could not be opened");
    expect(screen.queryByText("picker unavailable")).not.toBeInTheDocument();
  });

  it("atomically clears plan approval results warnings and report readiness when the brief changes", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(<App api={api} />);

    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    await screen.findByRole("heading", { name: "Results" });
    expect(screen.getByRole("heading", { name: "Warnings to review" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Study brief" }));
    await user.type(screen.getByRole("textbox", { name: "Research question" }), " Updated");

    expect(api.invalidateProject).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Results review" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Word report" })).toBeDisabled();
    expect(screen.queryByRole("heading", { name: "Warnings to review" })).not.toBeInTheDocument();
  });

  it("atomically clears dependent analysis state when a new dataset is selected", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi()} />);
    await openApprovedDataPlan(user);
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    await screen.findByRole("heading", { name: "Results" });

    await user.click(screen.getByRole("button", { name: "Data & variables" }));
    await user.click(screen.getByRole("button", { name: "Import Excel" }));

    expect(screen.getByRole("button", { name: "Approve data structure" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Accept remaining clear variables" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Analysis plan" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Results review" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Word report" })).toBeDisabled();
    expect(screen.queryByRole("heading", { name: "Warnings to review" })).not.toBeInTheDocument();
  });
});
