import { contextBridge, ipcRenderer } from "electron";
import { createBiostatBridge } from "./bridge.js";

contextBridge.exposeInMainWorld("biostat", createBiostatBridge(ipcRenderer.invoke));
