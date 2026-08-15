import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("biostat", {
  selectDataFile: (): Promise<string | null> => ipcRenderer.invoke("biostat:select-data-file"),
  selectProject: (): Promise<string | null> => ipcRenderer.invoke("biostat:select-project"),
  selectReportDestination: (): Promise<string | null> =>
    ipcRenderer.invoke("biostat:select-report-destination"),
  getApiSession: (): Promise<{ apiBase: string; token: string }> =>
    ipcRenderer.invoke("biostat:get-api-session"),
});
