// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { DataIntake } from "./DataIntake";
import type { AnalysisApi } from "../../api/client";

afterEach(cleanup);

const profile = { rows: 12, columns: 2, missing_cells: 1, sheets: ["Sheet1"], selected_sheet: "Sheet1", variables: {
  group: { display_name: "Group", kind: "binary", non_missing: 12, missing: 0, unique_values: 2 },
  outcome: { display_name: "Outcome", kind: "continuous", non_missing: 11, missing: 1, unique_values: 11 },
}, warnings: [{ code: "missing_values", column: "outcome", message: "Missing values require review." }] };

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
