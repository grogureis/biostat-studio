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

export interface BiostatBridge {
  selectDataFile(): Promise<string | null>;
  selectProject(): Promise<string | null>;
  selectReportDestination(): Promise<string | null>;
  requestApi(request: ApiRequest): Promise<ApiResponse>;
}

type Invoke = <T>(channel: string, payload?: unknown) => Promise<T>;

export function createBiostatBridge(invoke: Invoke): BiostatBridge {
  return Object.freeze({
    selectDataFile: (): Promise<string | null> => invoke("biostat:select-data-file"),
    selectProject: (): Promise<string | null> => invoke("biostat:select-project"),
    selectReportDestination: (): Promise<string | null> => invoke("biostat:select-report-destination"),
    requestApi: (request: ApiRequest): Promise<ApiResponse> => invoke("biostat:request-api", request),
  });
}
