interface PathCapability {
  id: string;
  displayName: string;
}

interface BiostatBridge {
  selectDataFile(): Promise<{
    displayName: string;
    profileCapability: string;
    importCapability: string;
  } | null>;
  selectProject(mode: "create" | "open"): Promise<PathCapability | null>;
  selectReportDestination(): Promise<PathCapability | null>;
  requestApi(request: {
    path: string;
    method: "GET" | "POST";
    body?: unknown;
  }): Promise<{ ok: boolean; status: number; body: unknown }>;
}

interface Window {
  biostat: BiostatBridge;
}
