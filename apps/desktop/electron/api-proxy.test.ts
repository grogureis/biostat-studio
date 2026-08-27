import { describe, expect, it, vi } from "vitest";

import { createAuthenticatedApiProxy } from "./api-proxy";
import { createPathCapabilityStore } from "./path-capabilities";

describe("authenticated main-process API proxy", () => {
  it("adds the secret in the main process and accepts only versioned relative routes", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ api: 1 }), { status: 200 }));
    const proxy = createAuthenticatedApiProxy(
      () => ({ apiBase: "http://127.0.0.1:4040", token: "main-only-secret" }),
      request,
    );

    await expect(proxy({ path: "/v1/session", method: "GET" })).resolves.toEqual({
      ok: true,
      status: 200,
      body: { api: 1 },
    });
    expect(request).toHaveBeenCalledWith("http://127.0.0.1:4040/v1/session", {
      method: "GET",
      headers: { Authorization: "Bearer main-only-secret" },
    });
    await expect(proxy({ path: "https://example.test/v1/session", method: "GET" })).rejects.toThrow("Invalid API request");
    await expect(proxy({ path: "/health", method: "GET" })).rejects.toThrow("Invalid API request");
    await expect(proxy({ path: "/v1/unapproved-capability", method: "GET" })).rejects.toThrow("Invalid API request");
  });

  it("allows the stateless power calculator through the desktop boundary", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      analysis: "two_sample_t",
      solve_for: "sample_size",
      per_group_rounded: 64,
      total_rounded: 128,
    }), { status: 200 }));
    const proxy = createAuthenticatedApiProxy(
      () => ({ apiBase: "http://127.0.0.1:4040", token: "main-only-secret" }),
      request,
    );

    await expect(proxy({
      path: "/v1/power",
      method: "POST",
      body: {
        analysis: "two_sample_t",
        solve_for: "sample_size",
        alpha: 0.05,
        power: 0.8,
        effect_size: 0.5,
      },
    })).resolves.toMatchObject({
      ok: true,
      body: { per_group_rounded: 64, total_rounded: 128 },
    });
  });
});

it("injects main-owned paths and rejects renderer-supplied raw paths", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "project" }), { status: 200 }));
  const ids = ["source-cap", "project-cap"];
  const capabilities = createPathCapabilityStore(() => ids.shift()!);
  capabilities.issue("data-import", "/private/source.xlsx", "source.xlsx");
  capabilities.issue("project-create", "/private/study.biostat", "study.biostat");
  const proxy = createAuthenticatedApiProxy(
    () => ({ apiBase: "http://127.0.0.1:4040", token: "secret" }), request, capabilities,
  );

  await proxy({
    path: "/v1/projects", method: "POST",
    body: { source_capability: "source-cap", project_capability: "project-cap", brief: { title: "Study" } },
  });
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({
    source_path: "/private/source.xlsx", project_root: "/private/study.biostat", brief: { title: "Study" },
  });

  await expect(proxy({
    path: "/v1/projects", method: "POST",
    body: { source_path: "/etc/passwd", brief: { title: "Study" } },
  })).rejects.toThrow("Invalid API request");
});

it("swaps a methodology capability for its path without widening the route allowlist", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ brief: {} }), { status: 200 }));
  const capabilities = createPathCapabilityStore(() => "methodology-cap");
  capabilities.issue("methodology-document", "/private/protocol.docx", "protocol.docx");
  const proxy = createAuthenticatedApiProxy(
    () => ({ apiBase: "http://127.0.0.1:4040", token: "secret" }), request, capabilities,
  );

  await proxy({
    path: "/v1/methodology/extract", method: "POST", body: { source_capability: "methodology-cap" },
  });
  expect(request.mock.calls[0][0]).toBe("http://127.0.0.1:4040/v1/methodology/extract");
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ source_path: "/private/protocol.docx" });

  await expect(proxy({
    path: "/v1/methodology/extract", method: "POST", body: { source_path: "/etc/passwd" },
  })).rejects.toThrow("Invalid API request");
  await expect(proxy({ path: "/v1/methodology", method: "POST", body: {} })).rejects.toThrow("Invalid API request");
  await expect(proxy({ path: "/v1/methodology/extract", method: "GET" })).rejects.toThrow("Invalid API request");
});

it("refuses to read a methodology document through a capability issued for tabular data", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ brief: {} }), { status: 200 }));
  const capabilities = createPathCapabilityStore(() => "profile-cap");
  capabilities.issue("data-profile", "/private/patient-study.xlsx", "patient-study.xlsx");
  const proxy = createAuthenticatedApiProxy(
    () => ({ apiBase: "http://127.0.0.1:4040", token: "secret" }), request, capabilities,
  );

  await expect(proxy({
    path: "/v1/methodology/extract", method: "POST", body: { source_capability: "profile-cap" },
  })).rejects.toThrow("Invalid path capability");
  expect(request).not.toHaveBeenCalled();
});

// Task 3: a project may already be open (e.g. reopened from disk) when the
// user attaches a methodology document to it, distinct from the /v1/projects
// creation path. This route carries only extracted text, never a filesystem
// path, so — unlike /v1/projects or /v1/methodology/extract above — it needs
// no capability injection; the existing source_path/project_root/destination
// rejection already guards the body.
it("allows attaching a methodology document to an open project", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ attached: true }), { status: 200 }));
  const proxy = createAuthenticatedApiProxy(
    () => ({ apiBase: "http://127.0.0.1:4040", token: "secret" }), request,
  );
  const uuid = "11111111-1111-4111-8111-111111111111";

  await expect(proxy({
    method: "POST",
    path: `/v1/projects/${uuid}/methodology`,
    body: { text: "Yöntem", source_sha256: "a".repeat(64), source_format: "docx", original_name: "y.docx", char_count: 6, truncated: false },
  })).resolves.toEqual({ ok: true, status: 200, body: { attached: true } });
});

it("allows requesting variable proposals for one open project", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ proposals: [], conflicts: [] }), { status: 200 }));
  const proxy = createAuthenticatedApiProxy(
    () => ({ apiBase: "http://127.0.0.1:4040", token: "secret" }), request,
  );
  const uuid = "11111111-1111-4111-8111-111111111111";

  await expect(proxy({
    method: "POST",
    path: `/v1/projects/${uuid}/variable-proposals`,
  })).resolves.toEqual({
    ok: true,
    status: 200,
    body: { proposals: [], conflicts: [] },
  });
});
