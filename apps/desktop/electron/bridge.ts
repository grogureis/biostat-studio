export interface ApiRequest {
  path: string;
  method: "GET" | "POST";
  body?: unknown;
}

export interface ApiResponse {
  ok: boolean;
  status: number;
  body: unknown;
}

export interface PathCapability {
  id: string;
  displayName: string;
}

export interface DataFileCapability {
  displayName: string;
  profileCapability: string;
  importCapability: string;
}

export interface BiostatBridge {
  selectDataFile(): Promise<DataFileCapability | null>;
  selectMethodologyDocument(): Promise<PathCapability | null>;
  selectProject(mode: "create" | "open"): Promise<PathCapability | null>;
  selectReportDestination(): Promise<PathCapability | null>;
  requestApi(request: ApiRequest): Promise<ApiResponse>;
}

type Invoke = <T>(channel: string, payload?: unknown) => Promise<T>;

export function createBiostatBridge(invoke: Invoke): BiostatBridge {
  return Object.freeze({
    selectDataFile: (): Promise<DataFileCapability | null> => invoke("biostat:select-data-file"),
    selectMethodologyDocument: (): Promise<PathCapability | null> => invoke("biostat:select-methodology-document"),
    selectProject: (mode: "create" | "open"): Promise<PathCapability | null> => invoke("biostat:select-project", mode),
    selectReportDestination: (): Promise<PathCapability | null> => invoke("biostat:select-report-destination"),
    requestApi: (request: ApiRequest): Promise<ApiResponse> => invoke("biostat:request-api", request),
  });
}
