interface FrameOwner {
  mainFrame: unknown;
}

interface IpcEvent {
  sender: unknown;
  senderFrame: unknown;
}

export function assertTrustedIpcSender(event: IpcEvent, expected: FrameOwner): void {
  if (event.sender !== expected || event.senderFrame !== expected.mainFrame) {
    throw new Error("Untrusted IPC sender");
  }
}
