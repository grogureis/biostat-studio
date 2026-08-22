import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createSidecarController,
  parseReadiness,
  resolveSidecarLaunchForEnvironment,
} from "./sidecar";

class ControlledChild extends EventEmitter {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  readonly signals: NodeJS.Signals[] = [];
  exitCode: number | null = null;
  killed = false;

  kill(signal: NodeJS.Signals): boolean {
    this.signals.push(signal);
    return true;
  }

  exit(code: number | null = 0, signal: NodeJS.Signals | null = null): void {
    this.exitCode = code;
    this.emit("exit", code, signal);
  }
}

afterEach(() => vi.useRealTimers());

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

  it("rejects ports outside the TCP range", () => {
    expect(() => parseReadiness('{"port":65536,"api":1}')).toThrow(
      "Invalid sidecar readiness",
    );
  });

  it("waits for SIGKILL child exit before rejecting timed-out startup", async () => {
    vi.useFakeTimers();
    const child = new ControlledChild();
    const controller = createSidecarController({
      spawn: () => child,
      resolveLaunch: () => ({ sidecarPath: "python", sidecarArgs: ["-m", "biostat_service.app"] }),
      createToken: () => "test-token",
      startupTimeoutMs: 10,
      stopTimeoutMs: 5,
    });

    const startup = controller.startSidecar();
    await vi.advanceTimersByTimeAsync(10);
    expect(child.signals).toEqual(["SIGTERM"]);

    await vi.advanceTimersByTimeAsync(5);
    expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);

    let settled = false;
    void startup.catch(() => {
      settled = true;
    });
    await Promise.resolve();
    expect(settled).toBe(false);

    child.exit(137, "SIGKILL");
    await expect(startup).rejects.toThrow("Timed out waiting for sidecar readiness");
  });

  it("keeps a failed startup shared while its child is terminating", async () => {
    const child = new ControlledChild();
    const controller = createSidecarController({
      spawn: () => child,
      resolveLaunch: () => ({ sidecarPath: "python", sidecarArgs: [] }),
      createToken: () => "test-token",
      startupTimeoutMs: 10,
      stopTimeoutMs: 5,
    });

    const firstStart = controller.startSidecar();
    child.emit("error", new Error("spawn failed"));
    const duplicateStart = controller.startSidecar();
    expect(duplicateStart).toBe(firstStart);

    child.exit(1);
    await expect(firstStart).rejects.toThrow("Unable to start sidecar: spawn failed");
  });

  it("restarts with a new session after an unexpected post-readiness exit", async () => {
    const firstChild = new ControlledChild();
    const secondChild = new ControlledChild();
    const children = [firstChild, secondChild];
    let spawnCount = 0;
    const controller = createSidecarController({
      spawn: () => children[spawnCount++]!,
      resolveLaunch: () => ({ sidecarPath: "python", sidecarArgs: [] }),
      createToken: () => `session-${spawnCount + 1}`,
    });

    const firstStart = controller.startSidecar();
    firstChild.stdout.write('{"port":43117,"api":1}\n');
    const firstSession = await firstStart;
    expect(controller.getSession()).toEqual(firstSession);

    firstChild.exit(1);
    expect(controller.getSession()).toBeUndefined();
    const secondStart = controller.startSidecar();
    expect(spawnCount).toBe(2);
    secondChild.stdout.write('{"port":43118,"api":1}\n');
    const secondSession = await secondStart;

    expect(secondSession).toEqual({
      apiBase: "http://127.0.0.1:43118",
      token: "session-2",
    });
    expect(secondSession).not.toEqual(firstSession);
  });

  it("shares concurrent termination and redacts the session token from startup errors", async () => {
    const child = new ControlledChild();
    const observedEnvironments: Array<Record<string, string | undefined>> = [];
    const controller = createSidecarController({
      spawn: (_path, _args, options) => {
        observedEnvironments.push(options.env);
        return child;
      },
      resolveLaunch: () => ({ sidecarPath: "python", sidecarArgs: [] }),
      createToken: () => "session-secret",
      startupTimeoutMs: 10,
      stopTimeoutMs: 5,
    });

    const startup = controller.startSidecar();
    child.stderr.write("launch failed for session-secret");
    child.emit("error", new Error("spawn failed"));
    expect(child.signals).toEqual(["SIGTERM"]);
    child.exit(1);
    await expect(startup).rejects.toThrow("launch failed for [redacted]");
    expect(observedEnvironments).toEqual([
      expect.objectContaining({ BIOSTAT_SESSION_TOKEN: "session-secret" }),
    ]);

    const readyChild = new ControlledChild();
    const readyController = createSidecarController({
      spawn: () => readyChild,
      resolveLaunch: () => ({ sidecarPath: "python", sidecarArgs: [] }),
      createToken: () => "next-session-secret",
      startupTimeoutMs: 10,
      stopTimeoutMs: 5,
    });
    const ready = readyController.startSidecar();
    readyChild.stdout.write('{"port":43117,"api":1}\n');
    await expect(ready).resolves.toMatchObject({ apiBase: "http://127.0.0.1:43117" });

    const firstStop = readyController.stopSidecar();
    const secondStop = readyController.stopSidecar();
    expect(firstStop).toBe(secondStop);
    expect(readyChild.signals).toEqual(["SIGTERM"]);
    readyChild.exit(null, "SIGTERM");
    await expect(Promise.all([firstStop, secondStop])).resolves.toEqual([undefined, undefined]);

    const noOpStop = readyController.stopSidecar();
    try {
      expect(readyChild.signals).toEqual(["SIGTERM"]);
    } finally {
      readyChild.exit(null, "SIGTERM");
      await noOpStop;
    }
  });

  it("prefers the packaged executable and otherwise resolves the repository-local virtual environment", () => {
    const packaged = resolveSidecarLaunchForEnvironment({
      resourcesPath: "/application/Contents/Resources",
      cwd: "/workspace/apps/desktop",
      exists: (path) => path === "/application/Contents/Resources/bin/biostat-service",
    });
    expect(packaged).toEqual({
      sidecarPath: "/application/Contents/Resources/bin/biostat-service",
      sidecarArgs: [],
    });

    const development = resolveSidecarLaunchForEnvironment({
      resourcesPath: "/application/Contents/Resources",
      cwd: "/workspace/apps/desktop",
      exists: (path) => path === "/workspace/services/analysis/.venv-py312/bin/python",
    });
    expect(development).toEqual({
      sidecarPath: "/workspace/services/analysis/.venv-py312/bin/python",
      sidecarArgs: ["-m", "biostat_service.app"],
    });
  });
});
