import { describe, expect, it } from "vitest";

import type { ArchitectureGraph } from "@/lib/api";

import { architectureGraphToMermaid } from "./architecture-export";

describe("architectureGraphToMermaid", () => {
  it("exports groups, responsibilities, and relations", () => {
    const graph = {
      repository_name: "example/repo",
      snapshot_id: "snap_1",
      commit_sha: "abc123",
      analysis_version: "architecture-graph-v2",
      summary: "summary",
      limitations: [],
      groups: [
        {
          id: "group_client",
          label: "Client",
          description: "UI",
          layer: "client",
          confidence: "verified",
          evidence: [],
        },
      ],
      nodes: [
        {
          id: "node_a",
          label: "Screen",
          responsibility: "Shows <results>",
          node_type: "component",
          group_id: "group_client",
          confidence: "verified",
          inputs: [],
          outputs: [],
          capability_ids: [],
          feature_flow_ids: [],
          evidence: [],
        },
        {
          id: "node_b",
          label: "API",
          responsibility: "Loads data",
          node_type: "api",
          group_id: null,
          confidence: "verified",
          inputs: [],
          outputs: [],
          capability_ids: [],
          feature_flow_ids: [],
          evidence: [],
        },
      ],
      edges: [
        {
          id: "edge_1",
          source: "node_a",
          target: "node_b",
          relation: "REQUESTS",
          label: "requests",
          description: "request",
          confidence: "verified",
          feature_flow_ids: [],
          evidence: [],
        },
      ],
    } satisfies ArchitectureGraph;

    const mermaid = architectureGraphToMermaid(graph);

    expect(mermaid).toContain("subgraph group_client");
    expect(mermaid).toContain("Shows &lt;results&gt;");
    expect(mermaid).toContain('node_a -->|"requests"| node_b');
  });
});
