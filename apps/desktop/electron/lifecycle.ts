export interface QuitEvent {
  preventDefault(): void;
}

export interface ApplicationLifecycleDependencies {
  startSidecar(): Promise<unknown>;
  stopSidecar(): Promise<void>;
  createWindow(): void;
  getWindowCount(): number;
  quit(): void;
  reportShutdownFailure(error: unknown): void;
}

export interface ApplicationLifecycle {
  initialize(): Promise<void>;
  activate(): void;
  beforeQuit(event: QuitEvent): Promise<void>;
}

export function createApplicationLifecycle(
  dependencies: ApplicationLifecycleDependencies,
): ApplicationLifecycle {
  let ready = false;
  let quitting = false;
  let exitAuthorized = false;
  let startPromise: Promise<void> | undefined;
  let stopPromise: Promise<void> | undefined;

  const maybeCreateWindow = (): void => {
    if (ready && !quitting && dependencies.getWindowCount() === 0) {
      dependencies.createWindow();
    }
  };

  const initialize = (): Promise<void> => {
    if (!startPromise) {
      startPromise = dependencies.startSidecar().then(() => {
        ready = true;
        maybeCreateWindow();
      });
    }
    return startPromise;
  };

  const activate = (): void => {
    maybeCreateWindow();
  };

  const beforeQuit = (event: QuitEvent): Promise<void> => {
    if (exitAuthorized) {
      return Promise.resolve();
    }
    event.preventDefault();
    if (stopPromise) {
      return stopPromise;
    }

    quitting = true;
    stopPromise = dependencies.stopSidecar().then(
      () => {
        exitAuthorized = true;
        dependencies.quit();
      },
      (error) => {
        dependencies.reportShutdownFailure(error);
        exitAuthorized = true;
        dependencies.quit();
      },
    );
    return stopPromise;
  };

  return { initialize, activate, beforeQuit };
}
