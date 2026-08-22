const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("node:path");

const digest = "a".repeat(64);
const revision = "11111111-1111-4111-8111-111111111111";
let jobRunCount = 0;
const pollCounts = new Map();
const cancelledJobs = new Set();
const reportLanguages = [];

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

const brief = {
  title: "Fixture study",
  question: "Is the outcome different between groups?",
  hypothesis: "The groups have different outcomes.",
  design: "cohort",
  outcome_variables: ["outcome"],
  exposure_variables: ["group"],
  covariates: [],
  language: "en",
};

const profile = {
  sheets: ["Analysis"], selected_sheet: "Analysis", rows: 12, columns: 2, missing_cells: 0,
  variables: {
    group: { display_name: "Group", kind: "binary", non_missing: 12, missing: 0, unique_values: 2 },
    outcome: { display_name: "Outcome", kind: "continuous", non_missing: 12, missing: 0, unique_values: 12 },
  },
  warnings: [],
};

const roles = [
  { name: "group", role: "exposure", kind: "binary", confirmed: true },
  { name: "outcome", role: "outcome", kind: "continuous", confirmed: true },
];

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, body };
}

function fixtureApi(request) {
  const { path: route, method } = request;
  const body = request.body ?? {};
  if (["source_path", "project_root", "destination"].some((key) => Object.prototype.hasOwnProperty.call(body, key))) {
    return response({ detail: "renderer_raw_path_rejected" }, 400);
  }
  if (route === "/v1/data/profile" && method === "POST") return response(profile);
  if (route === "/v1/projects" && method === "POST") return response({ id: "project-1", profile });
  if (route === "/v1/projects/open" && method === "POST") return response({ id: "project-1", brief, roles, plan, approved_plan: true, completed_job_id: "job-2", results: [result] });
  if (route === "/v1/projects/project-1/data-approval" && method === "POST") return response({ approved: true });
  if (route === "/v1/plans" && method === "POST") return response(plan);
  if (route === "/v1/plans/approval" && method === "POST") return response({ approved: true, revision, digest });
  if (route === "/v1/jobs" && method === "POST") {
    jobRunCount += 1;
    const id = `job-${jobRunCount}`;
    pollCounts.set(id, 0);
    return response({ id, status: "queued", progress: 0, message: "Analysis queued.", error_code: null, result: null });
  }
  const cancelMatch = route.match(/^\/v1\/jobs\/(job-\d+)\/cancel$/);
  if (cancelMatch && method === "POST") {
    cancelledJobs.add(cancelMatch[1]);
    return response({ id: cancelMatch[1], status: "cancelling", progress: 70, message: "Cancelling.", error_code: null, result: null });
  }
  const jobMatch = route.match(/^\/v1\/jobs\/(job-\d+)$/);
  if (jobMatch && method === "GET") {
    const id = jobMatch[1];
    const count = (pollCounts.get(id) ?? 0) + 1;
    pollCounts.set(id, count);
    if (cancelledJobs.has(id)) return response({ id, status: "cancelled", progress: 100, message: null, error_code: null, result: null });
    if (count === 1) return response({ id, status: "running", progress: 70, message: "Building publication figures.", error_code: null, result: null });
    return response({ id, status: "completed", progress: 100, message: "Publishing verified results.", error_code: null, result: { results: [result], warnings: [] } });
  }
  if (route === "/v1/reports" && method === "POST") {
    reportLanguages.push(request.body.language);
    return response({ saved: true, filename: `Fixture Results ${request.body.language}.docx` });
  }
  return response({ error: { code: "fixture_route_missing", message: "Fixture route is unavailable." } }, 404);
}

ipcMain.handle("biostat:select-data-file", () => ({ displayName: "12-observations.xlsx", profileCapability: "profile-cap", importCapability: "import-cap" }));
ipcMain.handle("biostat:select-project", (_event, mode) => ({ id: `${mode}-project-cap`, displayName: "Fixture project" }));
ipcMain.handle("biostat:select-report-destination", () => ({ id: `report-cap-${reportLanguages.length}`, displayName: "Fixture Results.docx" }));
ipcMain.handle("biostat:request-api", (_event, request) => fixtureApi(request));
ipcMain.handle("biostat:e2e-state", () => ({ jobRunCount, reportLanguages }));

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
