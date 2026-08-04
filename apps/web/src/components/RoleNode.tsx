import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BookOpen, CircleAlert, Sparkles } from "lucide-react";

import type { RepositoryStoryRole } from "@/lib/api";

export type RoleNodeData = RepositoryStoryRole & {
  dimmed?: boolean;
  flowOrdinal?: number | null;
  directImpact?: boolean;
  possibleImpact?: boolean;
  onActivate?: (roleId: string) => void;
};

export function RoleNode({ data, selected }: NodeProps) {
  const role = data as unknown as RoleNodeData;
  return (
    <article
      aria-label={`${role.display_name}. ${role.role_summary}`}
      className="story-role-node"
      data-dimmed={role.dimmed}
      data-direct-impact={role.directImpact}
      data-possible-impact={role.possibleImpact}
      data-selected={selected}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          role.onActivate?.(role.id);
        }
      }}
      role="button"
      tabIndex={0}
    >
      <Handle type="target" position={Position.Left} />
      <header>
        <span><Sparkles aria-hidden size={13} /> 역할</span>
        <small>{role.confidence === "verified" ? "근거 확인" : "분석 추론"}</small>
      </header>
      <strong>{role.display_name}</strong>
      <p>{role.role_summary}</p>
      <footer>
        <span><BookOpen aria-hidden size={12} /> {role.member_file_ids.length}개 근거 파일</span>
        {role.possibleImpact ? <CircleAlert aria-label="변경 영향 확인 필요" size={14} /> : null}
      </footer>
      {role.flowOrdinal ? <b aria-label={`기능 흐름 ${role.flowOrdinal}단계`}>{role.flowOrdinal}</b> : null}
      <Handle type="source" position={Position.Right} />
    </article>
  );
}
