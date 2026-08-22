import { describe, expect, it } from "vitest";

import { createPathCapabilityStore } from "./path-capabilities";

describe("main-owned path capabilities", () => {
  it("reveals only an opaque id and display name, then consumes the path once in scope", () => {
    const store = createPathCapabilityStore(() => "opaque-id");
    const capability = store.issue("data-profile", "/private/patient-study.xlsx", "patient-study.xlsx");

    expect(capability).toEqual({ id: "opaque-id", displayName: "patient-study.xlsx" });
    expect(JSON.stringify(capability)).not.toContain("/private/");
    expect(store.consume("opaque-id", "data-profile")).toBe("/private/patient-study.xlsx");
    expect(() => store.consume("opaque-id", "data-profile")).toThrow("Invalid path capability");
  });

  it("does not let profiling authority create a project", () => {
    const store = createPathCapabilityStore(() => "profile-id");
    store.issue("data-profile", "/private/study.xlsx", "study.xlsx");

    expect(() => store.consume("profile-id", "data-import")).toThrow("Invalid path capability");
    expect(store.consume("profile-id", "data-profile")).toBe("/private/study.xlsx");
  });

  it("does not consume a capability when the requested operation has the wrong scope", () => {
    const store = createPathCapabilityStore(() => "project-id");
    store.issue("project-open", "/private/study.biostat", "study.biostat");

    expect(() => store.consume("project-id", "project-create")).toThrow("Invalid path capability");
    expect(store.consume("project-id", "project-open")).toBe("/private/study.biostat");
  });
});
