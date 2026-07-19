import { describe, expect, it } from "vitest";

import type { TreeNode } from "./api";
import { collectDirectoryPaths, findFirstFile } from "./tree";

const tree: TreeNode[] = [
  {
    id: "dir:src",
    name: "src",
    path: "src",
    type: "directory",
    file_id: null,
    language: null,
    children: [
      {
        id: "file_page",
        name: "page.tsx",
        path: "src/page.tsx",
        type: "file",
        file_id: "file_page",
        language: "tsx",
        children: [],
      },
    ],
  },
];

describe("tree utilities", () => {
  it("finds the first nested file", () => {
    expect(findFirstFile(tree)?.file_id).toBe("file_page");
  });

  it("collects open directory paths", () => {
    expect(collectDirectoryPaths(tree)).toEqual(["src"]);
  });
});
