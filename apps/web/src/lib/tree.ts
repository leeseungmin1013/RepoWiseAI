import type { TreeNode } from "./api";

export function findFirstFile(nodes: TreeNode[]): TreeNode | null {
  for (const node of nodes) {
    if (node.type === "file") {
      return node;
    }
    const nested = findFirstFile(node.children);
    if (nested) {
      return nested;
    }
  }
  return null;
}

export function collectDirectoryPaths(nodes: TreeNode[], depth = 0): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.type !== "directory") {
      continue;
    }
    if (depth < 2) {
      paths.push(node.path);
    }
    paths.push(...collectDirectoryPaths(node.children, depth + 1));
  }
  return paths;
}
