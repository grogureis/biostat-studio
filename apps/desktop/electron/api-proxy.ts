import type { ApiRequest, ApiResponse } from "./bridge.js";
import type { SidecarSession } from "./sidecar.js";
import type { PathCapabilityStore, PathCapabilityScope } from "./path-capabilities.js";

type Request = (input: string, init: RequestInit) => Promise<Response>;
type SessionProvider = () => SidecarSession | Promise<SidecarSession>;

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const API_CAPABILITIES: ReadonlyArray<{ method: ApiRequest["method"]; route: RegExp }> = [
  { method: "GET", route: /^\/v1\/session$/ },
  {
    method: "POST",
    route: /^\/v1\/(?:data\/profile|methodology\/extract|projects|projects\/open|plans|plans\/approval|jobs|reports)$/,
  },
  { method: "POST", route: new RegExp(`^/v1/projects/${UUID}/data-approval$`) },
  // Carries extracted text, not a path, so unlike the routes above it needs
  // no capability injection — the source_path/project_root/destination
  // rejection below already keeps a filesystem path out of this body.
  { method: "POST", route: new RegExp(`^/v1/projects/${UUID}/methodology$`) },
  { method: "GET", route: new RegExp(`^/v1/jobs/${UUID}$`) },
  { method: "POST", route: new RegExp(`^/v1/jobs/${UUID}/cancel$`) },
];

function isApprovedCapability(request: ApiRequest): boolean {
  return API_CAPABILITIES.some(({ method, route }) => (
    request.method === method && route.test(request.path)
  ));
}

export function createAuthenticatedApiProxy(
  session: SessionProvider,
  request: Request = fetch,
  capabilities?: PathCapabilityStore,
): (apiRequest: ApiRequest) => Promise<ApiResponse> {
  return async (apiRequest) => {
    if (
      !apiRequest
      || !isApprovedCapability(apiRequest)
      || (apiRequest.method === "GET" && apiRequest.body !== undefined)
    ) {
      throw new Error("Invalid API request");
    }
    let body = apiRequest.body;
    if (body !== undefined) {
      if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Invalid API request");
      const supplied = body as Record<string, unknown>;
      if (["source_path", "project_root", "destination"].some((key) => key in supplied)) {
        throw new Error("Invalid API request");
      }
      const inject = (capabilityKey: string, pathKey: string, scope: PathCapabilityScope): void => {
        if (!(capabilityKey in supplied)) return;
        const id = supplied[capabilityKey];
        if (!capabilities || typeof id !== "string") throw new Error("Invalid API request");
        const path = capabilities.consume(id, scope);
        const { [capabilityKey]: _removed, ...remaining } = supplied;
        body = { ...remaining, [pathKey]: path };
      };
      if (apiRequest.path === "/v1/data/profile") inject("source_capability", "source_path", "data-profile");
      if (apiRequest.path === "/v1/methodology/extract") {
        inject("source_capability", "source_path", "methodology-document");
      }
      if (apiRequest.path === "/v1/projects") {
        inject("source_capability", "source_path", "data-import");
        if (body && typeof body === "object") {
          const current = body as Record<string, unknown>;
          if ("project_capability" in current) {
            const id = current.project_capability;
            if (!capabilities || typeof id !== "string") throw new Error("Invalid API request");
            const { project_capability: _removed, ...remaining } = current;
            body = { ...remaining, project_root: capabilities.consume(id, "project-create") };
          }
        }
      }
      if (apiRequest.path === "/v1/projects/open") inject("project_capability", "project_root", "project-open");
      if (apiRequest.path === "/v1/reports") inject("destination_capability", "destination", "report-save");
    }
    const active = await session();
    const response = await request(`${active.apiBase}${apiRequest.path}`, {
      method: apiRequest.method,
      headers: {
        Authorization: `Bearer ${active.token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    return {
      ok: response.ok,
      status: response.status,
      body: await response.json() as unknown,
    };
  };
}
