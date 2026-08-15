import { contextBridge, ipcRenderer } from "electron";
import { createBiostatBridge } from "./bridge";

contextBridge.exposeInMainWorld("biostat", createBiostatBridge(ipcRenderer.invoke));
