import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";
import { createInterface } from "node:readline";

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

interface SidecarLaunch {
  sidecarPath: string;
  sidecarArgs: string[];
}

type SidecarChild = ChildProcessByStdio<null, Readable, Readable>;

let activeChild: SidecarChild | undefined;
let activeSession: SidecarSession | undefined;
let starting: Promise<SidecarSession> | undefined;

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

function findDevelopmentRoot(): string {
  const candidates = [process.cwd(), resolve(process.cwd(), "../.."), resolve(process.cwd(), "../../..")];
  const root = candidates.find((candidate) =>
    existsSync(join(candidate, "services", "analysis", ".venv", "bin", "python")),
  );

  if (!root) {
    throw new Error("Local analysis environment is unavailable");
  }

  return root;
}

function resolveSidecarLaunch(): SidecarLaunch {
  const packagedSidecar = join(process.resourcesPath, "bin", "biostat-service");
  if (existsSync(packagedSidecar)) {
    return { sidecarPath: packagedSidecar, sidecarArgs: [] };
  }

  const root = findDevelopmentRoot();
  return {
    sidecarPath: join(root, "services", "analysis", ".venv", "bin", "python"),
    sidecarArgs: ["-m", "biostat_service.app"],
  };
}

function sanitizeStderr(value: string, token: string): string {
  return value
    .replaceAll(token, "[redacted]")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/[^\x20-\x7E]/g, "?")
    .trim()
    .slice(0, 1024);
}

function stopChild(child: SidecarChild): void {
  if (child.exitCode === null && !child.killed) {
    child.kill("SIGTERM");
  }
}

export function startSidecar(): Promise<SidecarSession> {
  if (activeSession) {
    return Promise.resolve(activeSession);
  }
  if (starting) {
    return starting;
  }

  const token = randomBytes(32).toString("hex");
  const { sidecarPath, sidecarArgs } = resolveSidecarLaunch();
  starting = new Promise<SidecarSession>((resolveStart, rejectStart) => {
    const child = spawn(sidecarPath, [...sidecarArgs, "--port", "0"], {
      env: { ...process.env, BIOSTAT_SESSION_TOKEN: token },
      stdio: ["ignore", "pipe", "pipe"],
    });
    activeChild = child;

    let stderr = "";
    let settled = false;
    const readinessReader = createInterface({ input: child.stdout });
    const timeout = setTimeout(() => fail("Timed out waiting for sidecar readiness"), STARTUP_TIMEOUT_MS);

    const finish = (): void => {
      clearTimeout(timeout);
      readinessReader.close();
      starting = undefined;
    };

    const fail = (reason: string): void => {
      if (settled) {
        return;
      }
      settled = true;
      finish();
      if (activeChild === child) {
        activeChild = undefined;
      }
      stopChild(child);
      const details = sanitizeStderr(stderr, token);
      rejectStart(new Error(details ? `${reason}: ${details}` : reason));
    };

    child.stderr.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString()}`.slice(-4096);
    });
    child.once("error", (error) => fail(`Unable to start sidecar: ${error.message}`));
    child.once("exit", (code, signal) => {
      if (!settled) {
        fail(`Sidecar exited before readiness (code ${code ?? "none"}, signal ${signal ?? "none"})`);
      }
      if (activeChild === child) {
        activeChild = undefined;
        activeSession = undefined;
      }
    });
    readinessReader.once("line", (line) => {
      try {
        const readiness = parseReadiness(line);
        settled = true;
        finish();
        activeSession = {
          apiBase: `http://127.0.0.1:${readiness.port}`,
          token,
        };
        resolveStart(activeSession);
      } catch {
        fail("Invalid sidecar readiness");
      }
    });
  });

  return starting;
}

export async function stopSidecar(): Promise<void> {
  const child = activeChild;
  activeChild = undefined;
  activeSession = undefined;
  starting = undefined;

  if (!child || child.exitCode !== null || child.killed) {
    return;
  }

  await new Promise<void>((resolveStop) => {
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      resolveStop();
    }, STOP_TIMEOUT_MS);
    child.once("exit", () => {
      clearTimeout(timeout);
      resolveStop();
    });
    child.kill("SIGTERM");
  });
}
