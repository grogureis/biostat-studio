export interface ApiSession {
  apiBase: string;
  token: string;
}

export interface BiostatBridge {
  selectDataFile(): Promise<string | null>;
  selectProject(): Promise<string | null>;
  selectReportDestination(): Promise<string | null>;
  getApiSession(): Promise<ApiSession>;
}

type Invoke = <T>(channel: string) => Promise<T>;

export function createBiostatBridge(invoke: Invoke): BiostatBridge {
  return Object.freeze({
    selectDataFile: (): Promise<string | null> => invoke("biostat:select-data-file"),
    selectProject: (): Promise<string | null> => invoke("biostat:select-project"),
    selectReportDestination: (): Promise<string | null> => invoke("biostat:select-report-destination"),
    getApiSession: (): Promise<ApiSession> => invoke("biostat:get-api-session"),
  });
}
