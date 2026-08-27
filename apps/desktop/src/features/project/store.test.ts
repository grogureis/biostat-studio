// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OpenProjectSnapshot } from "../../api/client";
import type { MethodologyExtraction, StudyBrief } from "../../api/types";
import { useProjectStore } from "./store";

const brief: StudyBrief = {
  title: "Comparison",
  question: "Does treatment change the outcome?",
  hypothesis: "Treatment is associated with a difference.",
  design: "cohort",
  outcome_variables: ["outcome"],
};

const extraction: MethodologyExtraction = {
  source_sha256: "a".repeat(64),
  source_format: "docx",
  original_name: "protokol.docx",
  char_count: 10,
  truncated: false,
  text: "Yöntem\nKesitsel çalışma.",
  warnings: [],
  brief: {
    title: null, question: null, hypothesis: null, design: null,
    outcome_concepts: [], exposure_concepts: [], covariate_concepts: [], warnings: [],
  },
};

const snapshot: OpenProjectSnapshot = {
  id: "project-1",
  brief,
  roles: [],
  plan: null,
  approved_plan: false,
  completed_job_id: null,
  results: [],
};

describe("project store", () => {
  it("nulls a carried methodology document on project restore", () => {
    const { result } = renderHook(() => useProjectStore());

    act(() => result.current.setMethodology(extraction));
    expect(result.current.methodology).toEqual(extraction);

    // OpenProjectSnapshot carries no methodology field of its own, so a
    // document extracted-but-not-yet-attached in an interrupted or crashed
    // session must not silently survive onto whichever project the restore
    // just opened.
    act(() => result.current.restoreProject(snapshot));

    expect(result.current.methodology).toBeNull();
  });
});
