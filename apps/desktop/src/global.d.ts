interface BiostatBridge {
  selectDataFile(): Promise<string | null>;
  selectProject(): Promise<string | null>;
  selectReportDestination(): Promise<string | null>;
  requestApi(request: {
    path: string;
    method: "GET" | "POST";
    body?: unknown;
  }): Promise<{ ok: boolean; status: number; body: unknown }>;
}

interface Window {
  biostat: BiostatBridge;
}
