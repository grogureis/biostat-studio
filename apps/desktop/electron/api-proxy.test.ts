import { describe, expect, it, vi } from "vitest";

import { createAuthenticatedApiProxy } from "./api-proxy";

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
});
