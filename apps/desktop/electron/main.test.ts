import { describe, expect, it, vi } from "vitest";
import { createBiostatBridge } from "./bridge";
import { createApplicationLifecycle } from "./lifecycle";
import { allowsRendererNavigation, requireLocalDevelopmentUrl } from "./renderer-security";

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("Electron lifecycle and renderer origin policy", () => {
  it("accepts only approved local HTTP development origins", () => {
    expect(requireLocalDevelopmentUrl("http://localhost:5173").origin).toBe("http://localhost:5173");
    expect(requireLocalDevelopmentUrl("http://127.0.0.1:5173").origin).toBe("http://127.0.0.1:5173");
    expect(() => requireLocalDevelopmentUrl("https://localhost:5173")).toThrow("local HTTP origin");
    expect(() => requireLocalDevelopmentUrl("http://example.test:5173")).toThrow("local HTTP origin");
    expect(() => requireLocalDevelopmentUrl("http://[::1]:5173")).toThrow("local HTTP origin");
  });

  it("allows navigation only within the approved renderer origin or exact packaged file", () => {
    expect(
      allowsRendererNavigation("http://localhost:5173/study", "http://localhost:5173/index.html"),
    ).toBe(true);
    expect(
      allowsRendererNavigation("http://127.0.0.1:5173", "http://localhost:5173/index.html"),
    ).toBe(false);
    expect(
      allowsRendererNavigation("https://example.test", "http://localhost:5173/index.html"),
    ).toBe(false);
    expect(
      allowsRendererNavigation("file:///app/dist/index.html", "file:///app/dist/index.html"),
    ).toBe(true);
    expect(
      allowsRendererNavigation("file:///app/dist/other.html", "file:///app/dist/index.html"),
    ).toBe(false);
  });

  it("does not create a renderer during startup and blocks every quit race until one stop completes", async () => {
    const startup = deferred();
    const shutdown = deferred();
    const createWindow = vi.fn();
    const quit = vi.fn();
    const lifecycle = createApplicationLifecycle({
      startSidecar: () => startup.promise,
      stopSidecar: () => shutdown.promise,
      createWindow,
      getWindowCount: () => 0,
      quit,
      reportShutdownFailure: vi.fn(),
    });

    const initialize = lifecycle.initialize();
    lifecycle.activate();
    expect(createWindow).not.toHaveBeenCalled();

    startup.resolve();
    await initialize;
    expect(createWindow).toHaveBeenCalledTimes(1);

    const firstQuit = { preventDefault: vi.fn() };
    const secondQuit = { preventDefault: vi.fn() };
    const firstShutdown = lifecycle.beforeQuit(firstQuit);
    const secondShutdown = lifecycle.beforeQuit(secondQuit);
    expect(firstQuit.preventDefault).toHaveBeenCalledTimes(1);
    expect(secondQuit.preventDefault).toHaveBeenCalledTimes(1);

    shutdown.resolve();
    await expect(Promise.all([firstShutdown, secondShutdown])).resolves.toEqual([undefined, undefined]);
    expect(quit).toHaveBeenCalledTimes(1);
  });

  it("exposes only the four approved renderer capabilities", async () => {
    const channels: string[] = [];
    const bridge = createBiostatBridge(async <T>(channel: string): Promise<T> => {
      channels.push(channel);
      return null as T;
    });

    expect(Object.keys(bridge)).toEqual([
      "selectDataFile",
      "selectProject",
      "selectReportDestination",
      "getApiSession",
    ]);
    await bridge.selectDataFile();
    await bridge.selectProject();
    await bridge.selectReportDestination();
    await bridge.getApiSession();
    expect(channels).toEqual([
      "biostat:select-data-file",
      "biostat:select-project",
      "biostat:select-report-destination",
      "biostat:get-api-session",
    ]);
  });
});
