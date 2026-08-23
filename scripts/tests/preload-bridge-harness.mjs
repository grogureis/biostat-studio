import { app, BrowserWindow } from "electron";

// Loads the built preload with the production webPreferences and reports which
// bridge methods reach the renderer. A sandboxed preload must be a
// self-contained CommonJS file; ESM syntax or relative requires fail silently
// in the main process and leave `window.biostat` undefined.
const preload = process.env.BIOSTAT_PRELOAD;
const expected = ["selectDataFile", "selectProject", "selectReportDestination", "requestApi"];

function fail(reason) {
  console.error(`preload_bridge_smoke_failed:${reason}`);
  app.exit(1);
}

app.whenReady().then(async () => {
  if (!preload) return fail("BIOSTAT_PRELOAD_unset");
  const window = new BrowserWindow({
    show: false,
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  let preloadError = null;
  window.webContents.on("preload-error", (_event, path, error) => {
    preloadError = `${path}:${error.message.split("\n")[0]}`;
  });
  await window.loadURL("data:text/html,<title>preload smoke</title>");
  const exposed = await window.webContents.executeJavaScript(
    'window.biostat ? Object.keys(window.biostat).filter((key) => typeof window.biostat[key] === "function") : null',
  );
  if (preloadError) return fail(`preload_error:${preloadError}`);
  if (exposed === null) return fail("bridge_not_exposed");
  const missing = expected.filter((method) => !exposed.includes(method));
  if (missing.length) return fail(`bridge_methods_missing:${missing.join(",")}`);
  console.log(`preload_bridge_smoke_passed:${exposed.join(",")}`);
  app.exit(0);
}).catch((error) => fail(`harness_error:${error.message}`));
