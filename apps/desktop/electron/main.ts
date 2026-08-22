import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { fileURLToPath, pathToFileURL } from "node:url";
import { basename, dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import { createApplicationLifecycle } from "./lifecycle.js";
import { allowsRendererNavigation, requireLocalDevelopmentUrl } from "./renderer-security.js";
import { getSidecarSession, startSidecar, stopSidecar, type SidecarSession } from "./sidecar.js";
import { createAuthenticatedApiProxy } from "./api-proxy.js";
import { createPathCapabilityStore } from "./path-capabilities.js";
import { assertTrustedIpcSender } from "./ipc-security.js";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
let mainWindow: BrowserWindow | undefined;
const pathCapabilities = createPathCapabilityStore(randomUUID);

function rendererUrl(): string {
  const developmentUrl = process.env.VITE_DEV_SERVER_URL;
  if (developmentUrl) {
    return requireLocalDevelopmentUrl(developmentUrl).toString();
  }
  return pathToFileURL(join(currentDirectory, "../dist/index.html")).toString();
}

function createWindow(): BrowserWindow {
  const approvedRenderer = rendererUrl();
  const window = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    webPreferences: {
      preload: join(currentDirectory, "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, target) => {
    if (!allowsRendererNavigation(target, approvedRenderer)) {
      event.preventDefault();
    }
  });
  void window.loadURL(approvedRenderer);

  return window;
}

async function requireSession(): Promise<SidecarSession> {
  return getSidecarSession() ?? startSidecar();
}

function registerIpcHandlers(): void {
  const trusted = (event: Electron.IpcMainInvokeEvent): void => {
    if (!mainWindow) throw new Error("The application window is unavailable");
    assertTrustedIpcSender(event, mainWindow.webContents);
  };
  ipcMain.handle("biostat:select-data-file", async (event) => {
    trusted(event);
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: [{ name: "Excel workbook", extensions: ["xlsx"] }],
    });
    const path = result.filePaths[0];
    if (result.canceled || !path) return null;
    return {
      displayName: basename(path),
      profileCapability: pathCapabilities.issue("data-profile", path, basename(path)).id,
      importCapability: pathCapabilities.issue("data-import", path, basename(path)).id,
    };
  });

  ipcMain.handle("biostat:select-project", async (event, mode: unknown) => {
    trusted(event);
    if (mode !== "create" && mode !== "open") throw new Error("Invalid project picker mode");
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: mode === "create" ? ["openDirectory", "createDirectory"] : ["openDirectory"],
    });
    const path = result.filePaths[0];
    return result.canceled || !path
      ? null
      : pathCapabilities.issue(mode === "create" ? "project-create" : "project-open", path, basename(path));
  });

  ipcMain.handle("biostat:select-report-destination", async (event) => {
    trusted(event);
    const result = await dialog.showSaveDialog(mainWindow!, {
      filters: [{ name: "Word document", extensions: ["docx"] }],
    });
    return result.canceled || !result.filePath
      ? null
      : pathCapabilities.issue("report-save", result.filePath, basename(result.filePath));
  });

  const requestApi = createAuthenticatedApiProxy(requireSession, fetch, pathCapabilities);
  ipcMain.handle("biostat:request-api", (event, request) => {
    trusted(event);
    return requestApi(request);
  });
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to start the local analysis service";
}

const lifecycle = createApplicationLifecycle({
  startSidecar: async () => {
    await startSidecar();
    registerIpcHandlers();
  },
  stopSidecar,
  createWindow: () => {
    mainWindow = createWindow();
  },
  getWindowCount: () => BrowserWindow.getAllWindows().length,
  quit: () => app.quit(),
  reportShutdownFailure: (error) => {
    dialog.showErrorBox("BioStat Studio sidecar shutdown failed", messageFor(error));
  },
});

app.whenReady().then(() => {
  void lifecycle.initialize().catch((error) => {
    dialog.showErrorBox("BioStat Studio could not start", messageFor(error));
    app.quit();
  });
});

app.on("activate", () => {
  lifecycle.activate();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", (event) => {
  void lifecycle.beforeQuit(event);
});
