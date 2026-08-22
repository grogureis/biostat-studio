export type PathCapabilityScope = "data-profile" | "data-import" | "project-create" | "project-open" | "report-save";

export interface PathCapability {
  id: string;
  displayName: string;
}

interface StoredCapability {
  scope: PathCapabilityScope;
  path: string;
}

export interface PathCapabilityStore {
  issue(scope: PathCapabilityScope, path: string, displayName: string): PathCapability;
  consume(id: string, scope: PathCapabilityScope): string;
}

export function createPathCapabilityStore(createId: () => string): PathCapabilityStore {
  const capabilities = new Map<string, StoredCapability>();
  return {
    issue(scope, path, displayName) {
      const id = createId();
      if (!id || capabilities.has(id)) throw new Error("Unable to issue path capability");
      capabilities.set(id, { scope, path });
      return Object.freeze({ id, displayName });
    },
    consume(id, scope) {
      const capability = capabilities.get(id);
      if (!capability || capability.scope !== scope) throw new Error("Invalid path capability");
      capabilities.delete(id);
      return capability.path;
    },
  };
}
