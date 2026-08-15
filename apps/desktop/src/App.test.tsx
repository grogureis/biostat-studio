// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { AnalysisApi } from "./api/client";
import type { AnalysisPlan, AnalysisResult } from "./api/types";

const plan: AnalysisPlan = {
  version: 1,
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

function fakeApi(overrides: Partial<AnalysisApi> = {}): AnalysisApi {
  return {
    selectDataFile: vi.fn().mockResolvedValue("/Users/research/core-study.xlsx"),
    createPlan: vi.fn().mockResolvedValue(plan),
    runAnalysis: vi.fn().mockResolvedValue([result]),
    cancelAnalysis: vi.fn().mockResolvedValue(undefined),
    exportReport: vi.fn().mockResolvedValue("/Users/research/Results.docx"),
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("Clinical Calm workflow", () => {
  it("presents six semantic stages and requires plan approval before analysis", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi()} />);

    expect(screen.getByRole("navigation", { name: "Analysis workflow" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^(Study brief|Data & variables|Analysis plan|Run & diagnose|Results review|Word report)$/ })).toHaveLength(6);
    expect(screen.getByText("Offline · data stays on this Mac")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
    expect(screen.getByRole("heading", { name: "Analysis plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeEnabled();
  });

  it("announces progress and supports cancellation without presenting partial results", async () => {
    const pending = deferred<AnalysisResult[]>();
    const api = fakeApi({ runAnalysis: vi.fn(() => pending.promise) });
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
    await user.click(screen.getByRole("checkbox", { name: "Approve this plan" }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(screen.getByRole("heading", { name: "Run & diagnose" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Running approved analysis");
    expect(screen.getByRole("progressbar", { name: "Analysis progress" })).toHaveAttribute("aria-valuenow", "42");

    await user.click(screen.getByRole("button", { name: "Cancel analysis" }));
    expect(api.cancelAnalysis).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent("Analysis cancelled. No partial results were accepted.");
    expect(screen.queryByRole("heading", { name: "Results" })).not.toBeInTheDocument();
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

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
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
    await user.click(screen.getByRole("button", { name: "Analiz planı" }));
    expect(await screen.findByText("Welch independent-samples t-test")).toBeInTheDocument();
    expect(api.createPlan).toHaveBeenCalledWith(expect.objectContaining({ language: "tr" }));
  });

  it("exports the Word report through an explicit accessible action", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
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

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
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

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
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
    await user.click(screen.getByRole("button", { name: "Analiz planı" }));
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

    await user.click(screen.getByRole("button", { name: "Analysis plan" }));
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

  it("handles a file-picker exception without exposing a path or crashing", async () => {
    const api = fakeApi({ selectDataFile: vi.fn().mockRejectedValue(new Error("picker unavailable")) });
    const user = userEvent.setup();
    render(<App api={api} />);

    await user.click(screen.getByRole("button", { name: "Data & variables" }));
    await user.click(screen.getByRole("button", { name: "Import Excel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The workbook picker could not be opened");
    expect(screen.queryByText("picker unavailable")).not.toBeInTheDocument();
  });
});
