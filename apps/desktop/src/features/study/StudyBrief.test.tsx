// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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
      original_name: "protokol.docx",
      char_count: 100,
      truncated: false,
      text: "Yöntem\nRetrospektif kohort çalışması.",
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
      original_name: "uzun-protokol.txt",
      char_count: 200000,
      truncated: true,
      text: "a".repeat(200000),
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
      original_name: "protokol.txt",
      char_count: 500,
      truncated: false,
      text: "Giriş\nKesitsel çalışma.",
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

// --- FINAL REVIEW: extraction used to discard whatever the brief gained while
// it was running. `update` closed over the `value` prop captured at click time
// and importDocument calls update("design", …) AFTER awaiting
// extractMethodology, so it wrote back a click-time snapshot. App.tsx hands
// that straight to store.ts, which replaces the whole brief object with no
// merge — so every field changed during the round trip was reverted.

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

const cohortExtraction: MethodologyExtraction = {
  source_sha256: "a".repeat(64),
  source_format: "docx",
  original_name: "protokol.docx",
  char_count: 100,
  truncated: false,
  text: "Yöntem\nRetrospektif kohort çalışması.",
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
};

/** Holds the brief the way App.tsx does, so onChange actually feeds `value` back. */
function Harness({ api }: { api: AnalysisApi }) {
  const [brief, setBrief] = useState<StudyBriefDto>(emptyBrief);
  return (
    <>
      <button type="button" onClick={() => setBrief((current) => ({ ...current, title: "kullanıcının yazdığı başlık" }))}>
        edit-title
      </button>
      <p data-testid="brief-state">{JSON.stringify(brief)}</p>
      <StudyBrief value={brief} onChange={setBrief} language="tr" api={api} />
    </>
  );
}

it("keeps a brief field that changed while the extraction was still in flight", async () => {
  const user = userEvent.setup();
  const pending = deferred<MethodologyExtraction>();
  const api = makeApi({ extractMethodology: vi.fn(() => pending.promise) });
  render(<Harness api={api} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));
  // The picker has resolved; the extraction round trip is still open.
  await screen.findByText("protokol.docx");

  await user.click(screen.getByRole("button", { name: "edit-title" }));

  pending.resolve(cohortExtraction);
  await screen.findByText(/Retrospektif kohort çalışması\./);

  const brief = JSON.parse(screen.getByTestId("brief-state").textContent ?? "{}") as StudyBriefDto;
  expect(brief.design).toBe("cohort");
  // Before the fix this was "" — the proposal write clobbered it.
  expect(brief.title).toBe("kullanıcının yazdığı başlık");
});

it("disables the import button and the form while the extraction runs, so no second run can start", async () => {
  const user = userEvent.setup();
  const pending = deferred<MethodologyExtraction>();
  const extractMethodology = vi.fn(() => pending.promise);
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={makeApi({ extractMethodology })} />);

  await user.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));
  await screen.findByText("protokol.docx");

  const busyButton = screen.getByRole("button", { name: /yükleniyor/i });
  expect(busyButton).toBeDisabled();
  expect(screen.getByLabelText(/proje başlığı/i)).toBeDisabled();
  expect(screen.getByLabelText(/araştırma sorusu/i)).toBeDisabled();
  expect(screen.getByLabelText(/çalışma tasarımı/i)).toBeDisabled();

  // Two rapid clicks used to start two concurrent importDocument runs, last
  // write wins. The disabled button plus the in-flight guard closes that.
  await user.click(busyButton);
  expect(extractMethodology).toHaveBeenCalledTimes(1);

  pending.resolve(cohortExtraction);
  await waitFor(() => expect(screen.getByRole("button", { name: /metodoloji dokümanı/i })).toBeEnabled());
  expect(screen.getByLabelText(/proje başlığı/i)).toBeEnabled();
});

it("labels the in-progress import in English too", async () => {
  const user = userEvent.setup();
  const pending = deferred<MethodologyExtraction>();
  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="en" api={makeApi({ extractMethodology: vi.fn(() => pending.promise) })} />);

  await user.click(screen.getByRole("button", { name: /import methodology document/i }));
  await screen.findByText("protokol.docx");

  expect(screen.getByRole("button", { name: /importing document…/i })).toBeDisabled();

  pending.resolve(cohortExtraction);
  await waitFor(() => expect(screen.getByRole("button", { name: /import methodology document/i })).toBeEnabled());
});

// --- Task 3: the project does not exist yet when the document is extracted
// (it is only created later, when the Excel workbook arrives), so the
// extracted text has nowhere to live except the renderer. StudyBrief keeps
// its local `extraction` state for the proposal badges, but must ALSO report
// the full extraction upward so App.tsx/store.ts can carry it forward to
// project creation.

it("lifts the extracted document out of the component", async () => {
  const onMethodology = vi.fn();
  const api = {
    selectMethodologyDocument: async () => "yontem.docx",
    extractMethodology: async () => ({
      source_sha256: "a".repeat(64),
      source_format: "docx",
      original_name: "yontem.docx",
      char_count: 24,
      truncated: false,
      text: "Yöntem\nKesitsel çalışma.",
      warnings: [],
      brief: { title: null, question: null, hypothesis: null, design: null, outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [] },
    }),
  };

  render(<StudyBrief value={emptyBrief} onChange={vi.fn()} onMethodology={onMethodology} language="tr" api={api as never} />);
  // The brief's snippet matched the button by /belge/i, but the TR label is
  // "Metodoloji dokümanı yükle" — no "belge" substring exists anywhere in
  // this component's copy. Matched the same way every other test in this
  // file locates the import button.
  await userEvent.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

  await waitFor(() => expect(onMethodology).toHaveBeenCalledWith(
    expect.objectContaining({ text: "Yöntem\nKesitsel çalışma.", original_name: "yontem.docx" }),
  ));
});
