import { expect, it } from "vitest";

import { projectDialogRequest } from "./project-dialog";

it("uses a named save dialog for a new project instead of writing into an arbitrary selected folder", () => {
  const request = projectDialogRequest("create");

  expect(request.kind).toBe("save");
  expect(request.options).toMatchObject({
    title: expect.stringMatching(/BioStat.*project/i),
    buttonLabel: expect.stringMatching(/create/i),
    defaultPath: expect.stringMatching(/\.biostat$/),
  });
});

it("keeps reopening an existing project as an explicit folder selection", () => {
  const request = projectDialogRequest("open");

  expect(request.kind).toBe("open");
  expect(request.options).toMatchObject({
    title: expect.stringMatching(/open.*BioStat.*project/i),
    properties: ["openDirectory"],
  });
});
