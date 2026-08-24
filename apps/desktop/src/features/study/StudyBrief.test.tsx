// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AnalysisApiError, type AnalysisApi } from "../../api/client";
import type { MethodologyExtraction, StudyBrief as StudyBriefDto } from "../../api/types";
import { StudyBrief } from "./StudyBrief";

afterEach(cleanup);

const emptyBrief: StudyBriefDto = {
  title: "",
  question: "",
  hypothesis: "",
  design: "cross_sectional",
  outcome_variables: [],
};

const requiredStubs = {
  approveDataStructure: vi.fn(),
  createPlan: vi.fn(),
  approvePlan: vi.fn(),
  runAnalysis: vi.fn(),
  cancelAnalysis: vi.fn(),
  invalidateProject: vi.fn(),
  exportReport: vi.fn(),
  computePower: vi.fn(),
};

function makeApi(overrides: Partial<AnalysisApi> = {}): AnalysisApi {
  return {
    selectDataFile: vi.fn(),
    selectMethodologyDocument: vi.fn(async () => "protokol.docx"),
    extractMethodology: vi.fn(async (): Promise<MethodologyExtraction> => ({
      source_sha256: "a".repeat(64),
      source_format: "docx",
      char_count: 100,
      truncated: false,
      warnings: [],
      brief: {
        title: null,
        question: null,
        hypothesis: null,
        design: {
          value: "cohort",
          confidence: 0.7,
          evidence: "Retrospektif kohort çalışması.",
          evidence_offset: 7,
          source: "rule",
        },
        outcome_concepts: [],
        exposure_concepts: [],
        covariate_concepts: [],
        warnings: [],
      },
    })),
    ...requiredStubs,
    ...overrides,
  };
}

it("applies the proposed design and shows its evidence, using only the bare filename", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<StudyBrief value={emptyBrief} onChange={onChange} language="tr" api={makeApi()} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

  expect(await screen.findByText("protokol.docx")).toBeInTheDocument();
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ design: "cohort" }));
  expect(screen.getByText(/Retrospektif kohort çalışması\./)).toBeInTheDocument();
  // The renderer must never see or render a filesystem path — only the bare
  // filename the API client already resolved to a displayName.
  expect(screen.getByText("protokol.docx").textContent).toBe("protokol.docx");
});

it("tells the user when a scanned pdf carries no text, and tells them to re-select the file", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async () => {
      throw new AnalysisApiError(
        "methodology_intake_failed:no_extractable_text",
        "The local analysis service could not complete this operation.",
      );
    }),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={api} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/okunabilir metin/i);
  // Ruling 1: any failure invalidates the single-use capability token, so the
  // copy must tell the user to choose the file again, not to retry blindly.
  expect(alert).toHaveTextContent(/yeniden seç/i);
});

it("tells the English-speaking user to re-select the file too", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async () => {
      throw new AnalysisApiError(
        "methodology_intake_failed:unsupported_format",
        "The local analysis service could not complete this operation.",
      );
    }),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="en" api={api} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/not supported/i);
  expect(alert).toHaveTextContent(/again/i);
});

it("keys the error message off the AnalysisApiError code, not the message text", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async () => {
      // The message is deliberately generic — client.ts only puts the
      // structured code on `.code` for a 422 `detail` string. A handler that
      // string-splits `.message` would find nothing useful here.
      throw new AnalysisApiError(
        "methodology_intake_failed:file_too_large",
        "The local analysis service could not complete this operation.",
      );
    }),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="en" api={api} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/too large/i);
});

it("falls back to a generic, safe message for an error code it does not recognize", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async () => {
      throw new AnalysisApiError(
        "methodology_intake_failed:some_future_code",
        "The local analysis service could not complete this operation.",
      );
    }),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="en" api={api} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));

  const alert = await screen.findByRole("alert");
  expect(alert).toBeInTheDocument();
  // The raw, unrecognized code must never be shown verbatim to the user.
  expect(alert).not.toHaveTextContent("some_future_code");
});

it("reports the locally-thrown not-selected code the same safe way", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async () => {
      throw new AnalysisApiError(
        "methodology_document_not_selected",
        "Select a methodology document before requesting extraction.",
      );
    }),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="en" api={api} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));

  const alert = await screen.findByRole("alert");
  expect(alert).toBeInTheDocument();
  expect(alert).not.toHaveTextContent("methodology_document_not_selected");
});

it("warns when the document was truncated", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async (): Promise<MethodologyExtraction> => ({
      source_sha256: "a".repeat(64),
      source_format: "txt",
      char_count: 200000,
      truncated: true,
      warnings: ["document_truncated"],
      brief: {
        title: null, question: null, hypothesis: null, design: null,
        outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [],
      },
    })),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={api} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

  expect(await screen.findByText(/yalnızca ilk kısmı okundu/i)).toBeInTheDocument();
});

it("warns when no methods section was found, reading the merged top-level warnings", async () => {
  const user = userEvent.setup();
  const api = makeApi({
    extractMethodology: vi.fn(async (): Promise<MethodologyExtraction> => ({
      source_sha256: "a".repeat(64),
      source_format: "txt",
      char_count: 500,
      truncated: false,
      warnings: ["no_method_section"],
      brief: {
        title: null, question: null, hypothesis: null, design: null,
        outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [],
      },
    })),
  });
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={api} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

  expect(await screen.findByText(/yöntem bölümü bulunamadı/i)).toBeInTheDocument();
});

it("does nothing when the document picker is dismissed without a selection", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const api = makeApi({ selectMethodologyDocument: vi.fn(async () => null) });
  render(<StudyBrief value={emptyBrief} onChange={onChange} language="en" api={api} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));

  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
