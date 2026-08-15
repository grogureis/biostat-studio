import { randomBytes } from "node:crypto";
import { spawn, type ChildProcessByStdio } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import type { Readable } from "node:stream";

const STARTUP_TIMEOUT_MS = 15_000;
const STOP_TIMEOUT_MS = 5_000;

export interface SidecarReadiness {
  port: number;
  api: 1;
}

export interface SidecarSession {
  apiBase: string;
  token: string;
}

export interface SidecarLaunch {
  sidecarPath: string;
  sidecarArgs: string[];
}

export interface SidecarChild {
  stdout: Readable;
  stderr: Readable;
  exitCode: number | null;
  killed: boolean;
  kill(signal: NodeJS.Signals): boolean;
  once(event: "error", listener: (error: Error) => void): unknown;
  once(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): unknown;
}

export interface SidecarControllerDependencies {
  spawn: (
    sidecarPath: string,
    sidecarArgs: string[],
    options: { env: NodeJS.ProcessEnv; stdio: ["ignore", "pipe", "pipe"] },
  ) => SidecarChild;
  resolveLaunch: () => SidecarLaunch;
  createToken: () => string;
  startupTimeoutMs?: number;
  stopTimeoutMs?: number;
}

export interface SidecarController {
  startSidecar(): Promise<SidecarSession>;
  stopSidecar(): Promise<void>;
}

export function parseReadiness(line: string): SidecarReadiness {
  try {
    const value: unknown = JSON.parse(line);
    if (!value || typeof value !== "object") {
      throw new Error("Invalid sidecar readiness");
    }
    const { port, api } = value as Record<string, unknown>;
    if (!Number.isInteger(port) || Number(port) < 1 || api !== 1) {
      throw new Error("Invalid sidecar readiness");
    }
    return { port: Number(port), api: 1 };
  } catch {
    throw new Error("Invalid sidecar readiness");
  }
}

function findDevelopmentRoot(cwd: string, exists: (path: string) => boolean): string {
  const candidates = [cwd, resolve(cwd, "../.."), resolve(cwd, "../../..")];
  const root = candidates.find((candidate) =>
    exists(join(candidate, "services", "analysis", ".venv", "bin", "python")),
  );

  if (!root) {
    throw new Error("Local analysis environment is unavailable");
  }

  return root;
}

export function resolveSidecarLaunchForEnvironment({
  resourcesPath,
  cwd,
  exists,
}: {
  resourcesPath: string;
  cwd: string;
  exists: (path: string) => boolean;
}): SidecarLaunch {
  const packagedSidecar = join(resourcesPath, "bin", "biostat-service");
  if (exists(packagedSidecar)) {
    return { sidecarPath: packagedSidecar, sidecarArgs: [] };
  }

  const root = findDevelopmentRoot(cwd, exists);
  return {
    sidecarPath: join(root, "services", "analysis", ".venv", "bin", "python"),
    sidecarArgs: ["-m", "biostat_service.app"],
  };
}

function resolveSidecarLaunch(): SidecarLaunch {
  return resolveSidecarLaunchForEnvironment({
    resourcesPath: process.resourcesPath,
    cwd: process.cwd(),
    exists: existsSync,
  });
}

function sanitizeStderr(value: string, token: string): string {
  return value
    .replaceAll(token, "[redacted]")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/[^\x20-\x7E]/g, "?")
    .trim()
    .slice(0, 1024);
}

function defaultDependencies(): SidecarControllerDependencies {
  return {
    spawn: (sidecarPath, sidecarArgs, options) =>
      spawn(sidecarPath, sidecarArgs, options) as ChildProcessByStdio<null, Readable, Readable>,
    resolveLaunch: resolveSidecarLaunch,
    createToken: () => randomBytes(32).toString("hex"),
  };
}

export function createSidecarController(
  overrides: Partial<SidecarControllerDependencies> = {},
): SidecarController {
  const dependencies = { ...defaultDependencies(), ...overrides };
  const startupTimeoutMs = dependencies.startupTimeoutMs ?? STARTUP_TIMEOUT_MS;
  const stopTimeoutMs = dependencies.stopTimeoutMs ?? STOP_TIMEOUT_MS;
  let activeChild: SidecarChild | undefined;
  let activeSession: SidecarSession | undefined;
  let startPromise: Promise<SidecarSession> | undefined;
  let stopPromise: Promise<void> | undefined;

  const terminateActiveChild = (): Promise<void> => {
    if (stopPromise) {
      return stopPromise;
    }

    const child = activeChild;
    if (!child || child.exitCode !== null) {
      return Promise.resolve();
    }

    stopPromise = new Promise<void>((resolveStop, rejectStop) => {
      let killTimeout: ReturnType<typeof setTimeout> | undefined;
      const hardFailureTimeout = setTimeout(() => {
        rejectStop(new Error("Sidecar did not exit after SIGKILL"));
      }, stopTimeoutMs * 2);
      const onExit = (): void => {
        if (killTimeout) {
          clearTimeout(killTimeout);
        }
        clearTimeout(hardFailureTimeout);
        if (activeChild === child) {
          activeChild = undefined;
          activeSession = undefined;
        }
        resolveStop();
      };

      child.once("exit", onExit);
      child.kill("SIGTERM");
      killTimeout = setTimeout(() => {
        child.kill("SIGKILL");
      }, stopTimeoutMs);
    }).finally(() => {
      if (activeChild === child && child.exitCode !== null) {
        activeChild = undefined;
        activeSession = undefined;
      }
      stopPromise = undefined;
    });

    return stopPromise;
  };

  const stopSidecar = (): Promise<void> => {
    activeSession = undefined;
    return terminateActiveChild();
  };

  const startSidecar = (): Promise<SidecarSession> => {
    if (activeSession) {
      return Promise.resolve(activeSession);
    }
    if (startPromise) {
      return startPromise;
    }
    if (stopPromise) {
      return stopPromise.then(startSidecar);
    }

    const token = dependencies.createToken();
    const { sidecarPath, sidecarArgs } = dependencies.resolveLaunch();
    const pendingStart = new Promise<SidecarSession>((resolveStart, rejectStart) => {
      const child = dependencies.spawn(sidecarPath, [...sidecarArgs, "--port", "0"], {
        env: { ...process.env, BIOSTAT_SESSION_TOKEN: token },
        stdio: ["ignore", "pipe", "pipe"],
      });
      activeChild = child;

      let stderr = "";
      let settled = false;
      let session: SidecarSession | undefined;
      const readinessReader = createInterface({ input: child.stdout });
      const timeout = setTimeout(() => {
        void fail("Timed out waiting for sidecar readiness");
      }, startupTimeoutMs);

      const finishStartup = (): void => {
        clearTimeout(timeout);
        readinessReader.close();
      };

      const fail = async (reason: string): Promise<void> => {
        if (settled) {
          return;
        }
        settled = true;
        finishStartup();
        const details = sanitizeStderr(stderr, token);
        try {
          await stopSidecar();
          rejectStart(new Error(details ? `${reason}: ${details}` : reason));
        } catch (error) {
          const terminationError = error instanceof Error ? error.message : "Sidecar termination failed";
          rejectStart(new Error(`${details ? `${reason}: ${details}` : reason}; ${terminationError}`));
        }
      };

      child.stderr.on("data", (chunk: Buffer) => {
        stderr = `${stderr}${chunk.toString()}`.slice(-4096);
      });
      child.once("error", (error) => {
        void fail(`Unable to start sidecar: ${error.message}`);
      });
      child.once("exit", (code, signal) => {
        if (!settled) {
          void fail(`Sidecar exited before readiness (code ${code ?? "none"}, signal ${signal ?? "none"})`);
        } else if (session && activeChild === child && activeSession === session) {
          activeChild = undefined;
          activeSession = undefined;
        }
      });
      readinessReader.once("line", (line) => {
        try {
          const readiness = parseReadiness(line);
          settled = true;
          finishStartup();
          session = {
            apiBase: `http://127.0.0.1:${readiness.port}`,
            token,
          };
          activeSession = session;
          resolveStart(session);
        } catch {
          void fail("Invalid sidecar readiness");
        }
      });
    });

    startPromise = pendingStart;
    pendingStart.then(
      () => {
        if (startPromise === pendingStart) {
          startPromise = undefined;
        }
      },
      () => {
        if (startPromise === pendingStart) {
          startPromise = undefined;
        }
      },
    );
    return pendingStart;
  };

  return { startSidecar, stopSidecar };
}

const controller = createSidecarController();

export const startSidecar = controller.startSidecar;
export const stopSidecar = controller.stopSidecar;
