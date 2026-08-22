const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("biostat", Object.freeze({
  selectDataFile: () => ipcRenderer.invoke("biostat:select-data-file"),
  selectProject: () => ipcRenderer.invoke("biostat:select-project"),
  selectReportDestination: () => ipcRenderer.invoke("biostat:select-report-destination"),
  requestApi: (request) => ipcRenderer.invoke("biostat:request-api", request),
  e2eState: () => ipcRenderer.invoke("biostat:e2e-state"),
}));
