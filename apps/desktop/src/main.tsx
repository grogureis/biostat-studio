import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createAnalysisApi } from "./api/client";
import "./styles/clinical-calm.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App api={createAnalysisApi(window.biostat)} /></StrictMode>);
