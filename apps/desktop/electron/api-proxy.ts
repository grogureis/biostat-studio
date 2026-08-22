import type { ApiRequest, ApiResponse } from "./bridge";
import type { SidecarSession } from "./sidecar";

type Request = (input: string, init: RequestInit) => Promise<Response>;
type SessionProvider = () => SidecarSession;

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const API_CAPABILITIES: ReadonlyArray<{ method: ApiRequest["method"]; route: RegExp }> = [
  { method: "GET", route: /^\/v1\/session$/ },
  { method: "POST", route: /^\/v1\/(?:data\/profile|projects|plans|plans\/approval|jobs|reports)$/ },
  { method: "POST", route: new RegExp(`^/v1/projects/${UUID}/data-approval$`) },
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
): (apiRequest: ApiRequest) => Promise<ApiResponse> {
  return async (apiRequest) => {
    if (
      !apiRequest
      || !isApprovedCapability(apiRequest)
      || (apiRequest.method === "GET" && apiRequest.body !== undefined)
    ) {
      throw new Error("Invalid API request");
    }
    const active = session();
    const response = await request(`${active.apiBase}${apiRequest.path}`, {
      method: apiRequest.method,
      headers: {
        Authorization: `Bearer ${active.token}`,
        ...(apiRequest.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(apiRequest.body === undefined ? {} : { body: JSON.stringify(apiRequest.body) }),
    });
    return {
      ok: response.ok,
      status: response.status,
      body: await response.json() as unknown,
    };
  };
}
