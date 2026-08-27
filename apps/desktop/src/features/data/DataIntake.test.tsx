// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { DataIntake } from "./DataIntake";
import { AnalysisApiError, type AnalysisApi } from "../../api/client";

afterEach(cleanup);

const profile = { rows: 12, columns: 2, missing_cells: 1, sheets: ["Sheet1"], selected_sheet: "Sheet1", variables: {
  group: { display_name: "Group", kind: "binary", non_missing: 12, missing: 0, unique_values: 2 },
  outcome: { display_name: "Outcome", kind: "continuous", non_missing: 11, missing: 1, unique_values: 11 },
}, warnings: [{ code: "missing_values", column: "outcome", message: "Missing values require review." }] };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

it("shows the parsed workbook and explains the project-save step before matching finishes", async () => {
  const user = userEvent.setup();
  const preparation = deferred<{ proposals: []; conflicts: [] }>();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
      profileData: vi.fn().mockResolvedValue(profile),
      prepareDataStructure: vi.fn().mockReturnValue(preparation.promise),
      approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(),
      cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null}
    approved={false}
    language="en"
    brief={{ title: "Study", question: "Question", hypothesis: "Hypothesis", design: "cohort", outcome_variables: ["outcome"], exposure_variables: ["group"] }}
    onFile={vi.fn()}
    onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));

  expect(await screen.findByText("12 observations")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(/choose where to save the local BioStat project/i);
  expect(screen.getByRole("button", { name: "Importing Excel…" })).toBeDisabled();

  preparation.resolve({ proposals: [], conflicts: [] });
  expect(await screen.findByRole("button", { name: "Import Excel" })).toBeEnabled();
});

it("shows only the structural observation count returned by the local profiler", async () => {
  const user = userEvent.setup();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("/private/study.xlsx"),
      profileData: vi.fn().mockResolvedValue(profile),
      approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(),
      cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null}
    approved={false}
    language="en"
    onFile={vi.fn()}
    onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));
  expect(await screen.findByText("12 observations")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Group" })).toBeInTheDocument();
  expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent?.includes("1 missing") === true)).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Role for Outcome" })).toBeInTheDocument();
  expect(screen.queryByText("/private/study.xlsx")).not.toBeInTheDocument();
});

it("invokes the explicit data approval action and presents its confirmed state", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn().mockResolvedValue(undefined);
  const api = {
    selectDataFile: vi.fn().mockResolvedValue("study.xlsx"), profileData: vi.fn().mockResolvedValue(profile), approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(),
    runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
  };
  const { rerender } = render(<DataIntake
    api={api}
    dataFile={null}
    approved={false}
    language="en"
    onFile={vi.fn()}
    onApproval={onApproval}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "Role for Group" }), "exposure");
  await user.selectOptions(screen.getByRole("combobox", { name: "Role for Outcome" }), "outcome");
  await user.click(await screen.findByRole("button", { name: "Approve data structure" }));
  expect(onApproval).toHaveBeenCalledOnce();

  rerender(<DataIntake
    api={api}
    dataFile="study.xlsx"
    approved
    language="en"
    onFile={vi.fn()}
    onApproval={onApproval}
  />);
  expect(screen.getByRole("button", { name: "Data structure approved" })).toBeDisabled();
});

it("does not treat inferred variable roles as human-confirmed", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn().mockResolvedValue(undefined);
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"), profileData: vi.fn().mockResolvedValue(profile), approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(),
      runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null}
    approved={false}
    language="en"
    onFile={vi.fn()}
    onApproval={onApproval}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));

  expect(await screen.findByRole("button", { name: "Approve data structure" })).toBeDisabled();
  expect(onApproval).not.toHaveBeenCalled();
});

it("bulk-accepts only clear variables and leaves conflicts unconfirmed", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn().mockResolvedValue(undefined);
  const api = {
    selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
    profileData: vi.fn().mockResolvedValue(profile),
    prepareDataStructure: vi.fn().mockResolvedValue({
      proposals: [
        { column: "group", role: null, kind: { value: "binary", confidence: 0.7, evidence: null, evidence_offset: null, source: "rule" } },
      ],
      conflicts: [{ column: "group", data_kind: "binary", document_kind: "categorical", evidence: "Group classification", evidence_offset: 0, methods_if_document: [], methods_if_data: [], blocked_if_document: [], blocked_if_data: [] }],
    }),
    approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
  } as unknown as AnalysisApi;
  render(<DataIntake
    api={api}
    dataFile={null}
    approved={false}
    language="en"
    brief={{ title: "Study", question: "Is group associated with outcome?", hypothesis: "Yes", design: "cohort", outcome_variables: ["outcome"], exposure_variables: ["group"] }}
    onFile={vi.fn()}
    onApproval={onApproval}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));
  await user.click(await screen.findByRole("button", { name: "Accept remaining clear variables" }));

  expect(screen.getByRole("button", { name: "Approve data structure" })).toBeDisabled();
  await user.selectOptions(screen.getByRole("combobox", { name: "Role for Group" }), "exposure");
  await user.click(screen.getByRole("button", { name: "Approve data structure" }));
  const submitted = onApproval.mock.calls.at(-1)?.[0] ?? [];
  expect(submitted.find((role: { name: string }) => role.name === "group")?.confirmed).toBe(true);
  expect(submitted.find((role: { name: string }) => role.name === "outcome")?.confirmed).toBe(true);
});

it("shows each conflict's evidence and planner cost before the variable list", async () => {
  const user = userEvent.setup();
  const api = {
    selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
    profileData: vi.fn().mockResolvedValue(profile),
    prepareDataStructure: vi.fn().mockResolvedValue({
      proposals: [],
      conflicts: [{
        column: "group", data_kind: "continuous", document_kind: "categorical",
        evidence: "Patients were classified by TNM stage I-IV.", evidence_offset: 120,
        methods_if_document: ["welch_anova"], methods_if_data: ["pearson_or_spearman"],
        blocked_if_document: [], blocked_if_data: [],
      }],
    }),
    approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
  } as unknown as AnalysisApi;

  render(<DataIntake
    api={api}
    dataFile={null}
    approved={false}
    language="en"
    brief={{ title: "Study", question: "Question", hypothesis: "Hypothesis", design: "cohort", outcome_variables: ["outcome"], exposure_variables: ["group"] }}
    onFile={vi.fn()}
    onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));

  const conflict = await screen.findByRole("group", { name: "Conflict for Group" });
  expect(conflict).toHaveTextContent("Patients were classified by TNM stage I-IV.");
  expect(conflict).toHaveTextContent("Welch ANOVA");
  expect(conflict).toHaveTextContent("Pearson or Spearman correlation");
  expect(conflict).not.toHaveTextContent("welch_anova");
  expect(screen.getByRole("button", { name: "Use document classification for Group" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Use data classification for Group" })).toBeEnabled();
  expect(conflict.compareDocumentPosition(screen.getByRole("heading", { name: "Group" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("localizes structural metadata and editable role options in Turkish", async () => {
  const user = userEvent.setup();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"), profileData: vi.fn().mockResolvedValue(profile), approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(),
      runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null}
    approved={false}
    language="tr"
    onFile={vi.fn()}
    onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Excel içe aktar" }));
  expect(await screen.findByText("12 gözlem")).toBeInTheDocument();
  expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent?.includes("1 eksik · 11 benzersiz") === true)).toBeInTheDocument();
  const role = screen.getByRole("combobox", { name: "Rol Outcome" });
  expect(role).toHaveTextContent("Sonuç");
  expect(role).toHaveTextContent("Maruziyet");
  expect(role).toHaveTextContent("Kovaryat");
});

it("shows a safe approval failure without exposing service details", async () => {
  const user = userEvent.setup();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"), profileData: vi.fn().mockResolvedValue(profile), approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(),
      runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null}
    approved={false}
    language="en"
    onFile={vi.fn()}
    onApproval={vi.fn().mockRejectedValue(new Error("/private/patient-001.xlsx"))}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "Role for Group" }), "exposure");
  await user.selectOptions(screen.getByRole("combobox", { name: "Role for Outcome" }), "outcome");
  await user.click(await screen.findByRole("button", { name: "Approve data structure" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Data structure approval could not be completed");
  expect(screen.queryByText("/private/patient-001.xlsx")).not.toBeInTheDocument();
});

it("distinguishes an unreadable workbook from a picker failure", async () => {
  const user = userEvent.setup();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
      profileData: vi.fn().mockRejectedValue(new AnalysisApiError("data_profile_failed", "safe")),
      approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null} approved={false} language="tr" onFile={vi.fn()} onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Excel içe aktar" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/Excel dosyası okunamadı/i);
  expect(alert).not.toHaveTextContent(/seçici açılamadı/i);
});

it("identifies an incomplete study brief instead of blaming the Excel picker", async () => {
  const user = userEvent.setup();
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
      profileData: vi.fn().mockResolvedValue(profile),
      prepareDataStructure: vi.fn().mockRejectedValue(new AnalysisApiError("validation_error", "safe")),
      approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null} approved={false} language="tr"
    brief={{ title: "", question: "", hypothesis: "", design: "cohort", outcome_variables: [] }}
    onFile={vi.fn()} onApproval={vi.fn()}
  />);

  await user.click(screen.getByRole("button", { name: "Excel içe aktar" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/çalışma özetindeki zorunlu alanları/i);
  expect(alert).not.toHaveTextContent(/seçici açılamadı/i);
});

it("shows local-AI variable evidence and keeps uncalibrated suggestions unconfirmed", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn();
  const localProposal = {
    value: "outcome", confidence: 0.79,
    evidence: "The primary outcome was clinical deterioration.",
    evidence_offset: 10, source: "local:qwen2.5:14b",
  };
  render(<DataIntake
    api={{
      selectDataFile: vi.fn().mockResolvedValue("study.xlsx"),
      profileData: vi.fn().mockResolvedValue(profile),
      prepareDataStructure: vi.fn().mockResolvedValue({
        proposals: [{ column: "outcome", role: localProposal, kind: null }],
        conflicts: [],
        engine: { requested: "local:qwen2.5:14b", used: "local:qwen2.5:14b", fallback_reason: null },
      }),
      approveDataStructure: vi.fn(), createPlan: vi.fn(), approvePlan: vi.fn(), runAnalysis: vi.fn(), cancelAnalysis: vi.fn(), invalidateProject: vi.fn(), exportReport: vi.fn(), computePower: vi.fn(),
    }}
    dataFile={null} approved={false} language="en"
    brief={{ title: "Study", question: "Is notification associated?", hypothesis: "It is associated.", design: "cohort", outcome_variables: ["clinical deterioration"] }}
    onFile={vi.fn()} onApproval={onApproval}
  />);

  await user.click(screen.getByRole("button", { name: "Import Excel" }));

  expect(await screen.findByText("The primary outcome was clinical deterioration.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Accept remaining clear variables" }));
  expect(screen.getByRole("button", { name: "Approve data structure" })).toBeDisabled();
  expect(onApproval).not.toHaveBeenCalled();
});
