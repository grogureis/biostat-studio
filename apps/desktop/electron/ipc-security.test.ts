import { describe, expect, it } from "vitest";

import { assertTrustedIpcSender } from "./ipc-security";

describe("IPC sender validation", () => {
  it("accepts only the active window main frame", () => {
    const mainFrame = {};
    const webContents = { mainFrame };
    expect(() => assertTrustedIpcSender({ sender: webContents, senderFrame: mainFrame }, webContents)).not.toThrow();
    expect(() => assertTrustedIpcSender({ sender: {}, senderFrame: mainFrame }, webContents)).toThrow("Untrusted IPC sender");
    expect(() => assertTrustedIpcSender({ sender: webContents, senderFrame: {} }, webContents)).toThrow("Untrusted IPC sender");
  });
});
