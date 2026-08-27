import type { OpenDialogOptions, SaveDialogOptions } from "electron";

export type ProjectDialogRequest =
  | { kind: "save"; options: SaveDialogOptions }
  | { kind: "open"; options: OpenDialogOptions };

export function projectDialogRequest(mode: "create" | "open"): ProjectDialogRequest {
  if (mode === "create") {
    return {
      kind: "save",
      options: {
        title: "Create BioStat project / BioStat projesi oluştur",
        buttonLabel: "Create project / Proje oluştur",
        nameFieldLabel: "Project folder / Proje klasörü:",
        defaultPath: "BioStat Project.biostat",
        showsTagField: false,
      },
    };
  }
  return {
    kind: "open",
    options: {
      title: "Open BioStat project / BioStat projesini aç",
      buttonLabel: "Open project / Projeyi aç",
      properties: ["openDirectory"],
    },
  };
}
