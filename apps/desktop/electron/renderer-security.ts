const LOCAL_RENDERER_HOSTS = new Set(["localhost", "127.0.0.1"]);

export function requireLocalDevelopmentUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Development renderer URL must be an approved local HTTP origin");
  }

  if (url.protocol !== "http:" || !LOCAL_RENDERER_HOSTS.has(url.hostname)) {
    throw new Error("Development renderer URL must be an approved local HTTP origin");
  }

  return url;
}

export function allowsRendererNavigation(target: string, approvedRenderer: string): boolean {
  try {
    const destination = new URL(target);
    const approved = new URL(approvedRenderer);
    if (approved.protocol === "file:") {
      return destination.protocol === "file:" && destination.pathname === approved.pathname;
    }
    return destination.origin === approved.origin;
  } catch {
    return false;
  }
}
