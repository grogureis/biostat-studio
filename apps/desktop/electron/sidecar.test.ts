import { describe, expect, it } from "vitest";
import { parseReadiness } from "./sidecar";

describe("parseReadiness", () => {
  it("accepts the versioned local service message", () => {
    expect(parseReadiness('{"port":43117,"api":1}')).toEqual({
      port: 43117,
      api: 1,
    });
  });

  it("rejects a non-loopback or malformed message", () => {
    expect(() => parseReadiness('{"port":"bad"}')).toThrow(
      "Invalid sidecar readiness",
    );
  });
});
