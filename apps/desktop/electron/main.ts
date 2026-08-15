import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { startSidecar, stopSidecar, type SidecarSession } from "./sidecar";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
let mainWindow: BrowserWindow | undefined;
let sidecarSession: SidecarSession | undefined;
let quitting = false;

function createWindow(): BrowserWindow {
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

  const developmentUrl = process.env.VITE_DEV_SERVER_URL;
  if (developmentUrl) {
    void window.loadURL(developmentUrl);
  } else {
    void window.loadFile(join(currentDirectory, "../dist/index.html"));
  }

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

  ipcMain.handle("biostat:get-api-session", () => {
    const session = requireSession();
    return { apiBase: session.apiBase, token: session.token };
  });
}

app.whenReady().then(async () => {
  try {
    sidecarSession = await startSidecar();
    registerIpcHandlers();
    mainWindow = createWindow();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to start the local analysis service";
    dialog.showErrorBox("BioStat Studio could not start", message);
    app.exit(1);
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    mainWindow = createWindow();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", (event) => {
  if (quitting) {
    return;
  }

  event.preventDefault();
  void stopSidecar().finally(() => {
    quitting = true;
    app.quit();
  });
});
