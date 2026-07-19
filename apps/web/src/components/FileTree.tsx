"use client";

import {
  ChevronRight,
  FileBraces,
  FileCode2,
  FileText,
  Folder,
  FolderOpen,
} from "lucide-react";
import { useState } from "react";

import type { TreeNode } from "@/lib/api";
import { collectDirectoryPaths } from "@/lib/tree";

type Props = {
  nodes: TreeNode[];
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
};

function FileIcon({ language }: { language: string | null }) {
  if (language === "markdown") {
    return <FileText aria-hidden size={15} />;
  }
  if (language === "json" || language === "yaml" || language === "toml") {
    return <FileBraces aria-hidden size={15} />;
  }
  return <FileCode2 aria-hidden size={15} />;
}

function Branch({
  node,
  depth,
  expanded,
  selectedFileId,
  onToggle,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  selectedFileId: string | null;
  onToggle: (path: string) => void;
  onSelectFile: (fileId: string) => void;
}) {
  if (node.type === "directory") {
    const isOpen = expanded.has(node.path);
    return (
      <li>
        <button
          className="tree-row tree-directory"
          style={{ paddingLeft: 10 + depth * 14 }}
          onClick={() => onToggle(node.path)}
          type="button"
        >
          <ChevronRight className={isOpen ? "chevron-open" : ""} aria-hidden size={14} />
          {isOpen ? <FolderOpen aria-hidden size={15} /> : <Folder aria-hidden size={15} />}
          <span>{node.name}</span>
        </button>
        {isOpen ? (
          <ul>
            {node.children.map((child) => (
              <Branch
                key={child.id}
                node={child}
                depth={depth + 1}
                expanded={expanded}
                selectedFileId={selectedFileId}
                onToggle={onToggle}
                onSelectFile={onSelectFile}
              />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }

  return (
    <li>
      <button
        className={`tree-row tree-file ${selectedFileId === node.file_id ? "is-selected" : ""}`}
        style={{ paddingLeft: 28 + depth * 14 }}
        onClick={() => node.file_id && onSelectFile(node.file_id)}
        type="button"
      >
        <FileIcon language={node.language} />
        <span>{node.name}</span>
      </button>
    </li>
  );
}

export function FileTree({ nodes, selectedFileId, onSelectFile }: Props) {
  const [expanded, setExpanded] = useState(() => new Set(collectDirectoryPaths(nodes)));

  function toggle(path: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  return (
    <nav className="file-tree" aria-label="Repository files">
      <ul>
        {nodes.map((node) => (
          <Branch
            key={node.id}
            node={node}
            depth={0}
            expanded={expanded}
            selectedFileId={selectedFileId}
            onToggle={toggle}
            onSelectFile={onSelectFile}
          />
        ))}
      </ul>
    </nav>
  );
}
