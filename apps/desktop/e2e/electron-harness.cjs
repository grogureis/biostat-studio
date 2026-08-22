const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("node:path");

const digest = "a".repeat(64);
const revision = "11111111-1111-4111-8111-111111111111";
let pollCount = 0;

const plan = {
  version: 1,
  revision,
  digest,
  items: [{
    id: "primary",
    estimand: "Difference in outcome means between groups.",
    method: "welch_t_test",
    rationale: "Fixture plan for the deterministic Electron smoke workflow.",
    required_variables: ["outcome", "group"],
    assumptions: ["Independent observations"],
    robust_alternative: "mann_whitney_u",
    multiplicity_strategy: "not_applicable",
    outputs: ["mean_difference"],
    blocking_errors: [],
    warnings: [],
  }],
  blocking_errors: [],
  warnings: [],
};

const result = {
  id: "primary",
  method: "welch_t_test",
  n: 12,
  estimate: 2.5,
  p_value: 0.03,
  confidence_interval: { level: 0.95, lower: 0.3, upper: 4.7 },
  effect_size: { name: "Hedges' g", value: 0.7 },
  provenance: {
    data_fingerprint: "b".repeat(64),
    plan_version: 1,
    exclusions: [],
    transformations: [],
    random_seed: null,
    library_versions: { scipy: "fixture" },
  },
  diagnostics: {},
  exclusions: [],
  warnings: [],
};

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, body };
}

function fixtureApi(request) {
  const { path: route, method } = request;
  if (route === "/v1/data/profile" && method === "POST") return response({ rows: 12 });
  if (route === "/v1/projects" && method === "POST") return response({ id: "project-1", profile: { rows: 12 } });
  if (route === "/v1/projects/project-1/data-approval" && method === "POST") return response({ approved: true });
  if (route === "/v1/plans" && method === "POST") return response(plan);
  if (route === "/v1/plans/approval" && method === "POST") return response({ approved: true, revision, digest });
  if (route === "/v1/jobs" && method === "POST") {
    pollCount = 0;
    return response({ id: "job-1", status: "queued", progress: 0, message: "Analysis queued.", error_code: null, result: null });
  }
  if (route === "/v1/jobs/job-1" && method === "GET") {
    pollCount += 1;
    if (pollCount === 1) return response({ id: "job-1", status: "running", progress: 70, message: "Building publication figures.", error_code: null, result: null });
    return response({ id: "job-1", status: "completed", progress: 100, message: "Publishing verified results.", error_code: null, result: { results: [result], warnings: [] } });
  }
  if (route === "/v1/reports" && method === "POST") return response({ saved: true, filename: "Fixture Results.docx" });
  return response({ error: { code: "fixture_route_missing", message: "Fixture route is unavailable." } }, 404);
}

ipcMain.handle("biostat:select-data-file", () => "/fixture/12-observations.xlsx");
ipcMain.handle("biostat:select-project", () => "/fixture/project");
ipcMain.handle("biostat:select-report-destination", () => "/fixture/Fixture Results.docx");
ipcMain.handle("biostat:request-api", (_event, request) => fixtureApi(request));

app.whenReady().then(async () => {
  const window = new BrowserWindow({
    show: true,
    webPreferences: {
      preload: path.join(__dirname, "electron-preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  await window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
});

app.on("window-all-closed", () => app.quit());
