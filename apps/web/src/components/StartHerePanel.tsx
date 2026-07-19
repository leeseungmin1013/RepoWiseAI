"use client";

import { ArrowRight, BookOpenText, Boxes, CodeXml, GitCommitHorizontal } from "lucide-react";

import type { Snapshot, StartHere } from "@/lib/api";

type Props = {
  snapshot: Snapshot | null;
  startHere: StartHere | null;
  onOpenFile: (fileId: string) => void;
};

export function StartHerePanel({ snapshot, startHere, onOpenFile }: Props) {
  return (
    <aside className="guide-panel">
      <div className="panel-toolbar">
        <BookOpenText aria-hidden size={16} />
        <strong>Start Here</strong>
      </div>
      <StartHereContent snapshot={snapshot} startHere={startHere} onOpenFile={onOpenFile} />
    </aside>
  );
}

export function StartHereContent({ snapshot, startHere, onOpenFile }: Props) {
  if (!startHere || !snapshot) {
    return (
      <div className="panel-empty compact-empty">
        <span>분석이 완료되면 시작 지점이 표시됩니다.</span>
      </div>
    );
  }

  return (
    <div className="guide-scroll">
        <section className="guide-section repository-summary">
          <span className="section-kicker">Repository</span>
          <h2>{startHere.repository_name}</h2>
          <p>{startHere.summary}</p>
          <div className="commit-row" title={startHere.commit_sha}>
            <GitCommitHorizontal aria-hidden size={15} />
            <code>{startHere.commit_sha.slice(0, 10)}</code>
            <span>{snapshot.branch}</span>
          </div>
        </section>

        <section className="guide-section">
          <div className="section-heading">
            <CodeXml aria-hidden size={15} />
            <h3>기술 스택</h3>
          </div>
          <div className="tech-list">
            {startHere.tech_stack.length ? (
              startHere.tech_stack.map((tech) => <span key={tech}>{tech}</span>)
            ) : (
              <span>구조 분석 기준</span>
            )}
          </div>
        </section>

        <section className="guide-section">
          <div className="section-heading">
            <ArrowRight aria-hidden size={15} />
            <h3>진입점</h3>
          </div>
          <div className="entry-list">
            {startHere.entry_points.map((entry) => (
              <button key={entry.file_id} type="button" onClick={() => onOpenFile(entry.file_id)}>
                <span>{entry.path}</span>
                <small>{entry.reason}</small>
                <ArrowRight aria-hidden size={15} />
              </button>
            ))}
          </div>
        </section>

        <section className="guide-section">
          <div className="section-heading">
            <Boxes aria-hidden size={15} />
            <h3>주요 영역</h3>
          </div>
          <ul className="directory-list">
            {startHere.top_directories.map((directory) => (
              <li key={directory}>{directory}</li>
            ))}
          </ul>
        </section>
      </div>
  );
}
