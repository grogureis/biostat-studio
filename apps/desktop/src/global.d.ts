interface BiostatBridge {
  selectDataFile(): Promise<string | null>;
  selectProject(): Promise<string | null>;
  selectReportDestination(): Promise<string | null>;
  getApiSession(): Promise<{ apiBase: string; token: string }>;
}

interface Window {
  biostat: BiostatBridge;
}
