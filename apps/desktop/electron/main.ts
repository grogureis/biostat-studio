import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { createApplicationLifecycle } from "./lifecycle";
import { allowsRendererNavigation, requireLocalDevelopmentUrl } from "./renderer-security";
import { startSidecar, stopSidecar, type SidecarSession } from "./sidecar";
import { createAuthenticatedApiProxy } from "./api-proxy";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
let mainWindow: BrowserWindow | undefined;
let sidecarSession: SidecarSession | undefined;

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

function requireSession(): SidecarSession {
  if (!sidecarSession) {
    throw new Error("The local analysis service is unavailable");
  }
  return sidecarSession;
}

function registerIpcHandlers(): void {
  ipcMain.handle("biostat:select-data-file", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: [{ name: "Data files", extensions: ["xlsx", "xls", "csv", "sav"] }],
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });

  ipcMain.handle("biostat:select-project", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openDirectory", "createDirectory"],
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });

  ipcMain.handle("biostat:select-report-destination", async () => {
    const result = await dialog.showSaveDialog(mainWindow!, {
      filters: [{ name: "Word document", extensions: ["docx"] }],
    });
    return result.canceled ? null : result.filePath ?? null;
  });

  const requestApi = createAuthenticatedApiProxy(requireSession);
  ipcMain.handle("biostat:request-api", (_event, request) => requestApi(request));
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to start the local analysis service";
}

const lifecycle = createApplicationLifecycle({
  startSidecar: async () => {
    sidecarSession = await startSidecar();
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
