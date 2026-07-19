"use client";

import {
  BookOpenCheck,
  Braces,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  ExternalLink,
  FileCode2,
  GraduationCap,
  Lightbulb,
  ListTree,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
  RefreshCw,
  Send,
  Sparkles,
  Target,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import type {
  ActivityAttemptSummary,
  ChatAnswer,
  Citation,
  CodeSelection,
  LearningFeedbackType,
  LearningActivity,
  LearningLesson,
  LearningModule,
  LearningPath,
  LearningSession,
  RemediationBranch,
  RemediationMode,
  SourceFile,
  TeachingStyle,
} from "@/lib/api";

type Props = {
  path: LearningPath | null;
  session: LearningSession | null;
  remediation: RemediationBranch | null;
  activity: LearningActivity | null;
  activityAttempt: ActivityAttemptSummary | null;
  activityBusy: boolean;
  busy: boolean;
  file: SourceFile | null;
  selection: CodeSelection | null;
  answers: ChatAnswer[];
  asking: boolean;
  teachingStyle: TeachingStyle;
  onTeachingStyleChange: (style: TeachingStyle) => void;
  onOpenLesson: (learningModule: LearningModule, lesson: LearningLesson) => void;
  onFeedback: (lesson: LearningLesson, eventType: LearningFeedbackType) => void;
  onHelp: (mode: RemediationMode) => void;
  onCompleteHelp: () => void;
  onReplan: () => void;
  onSubmitActivity: (selectedChoiceId: string) => void;
  onAsk: (question: string) => Promise<void>;
  onOpenEvidence: (citation: Citation) => void;
  onOpenLines: (fileId: string, startLine: number, endLine: number) => void;
};

const HELP_ACTIONS: Array<{
  mode: RemediationMode;
  label: string;
  icon: typeof Braces;
}> = [
  { mode: "line_by_line", label: "문장별 설명", icon: ListTree },
  { mode: "prerequisite", label: "배경지식", icon: GraduationCap },
  { mode: "small_example", label: "작은 예제", icon: Lightbulb },
  { mode: "learning_sources", label: "공식 자료", icon: BookOpenCheck },
];

const QUICK_QUESTIONS = [
  "이 레슨의 코드를 실행 순서대로 설명해줘",
  "이 코드에 필요한 배경지식을 먼저 알려줘",
  "이 부분을 수정하면 어디에 영향이 생겨?",
];

export function LearningJourneyPanel({
  path,
  session,
  remediation,
  activity,
  activityAttempt,
  activityBusy,
  busy,
  file,
  selection,
  answers,
  asking,
  teachingStyle,
  onTeachingStyleChange,
  onOpenLesson,
  onFeedback,
  onHelp,
  onCompleteHelp,
  onReplan,
  onSubmitActivity,
  onAsk,
  onOpenEvidence,
  onOpenLines,
}: Props) {
  const [question, setQuestion] = useState("");
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  const current = findCurrent(path, session);

  useEffect(() => {
    if (answers.length || asking) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [answers, asking]);

  if (!path || !session || !current) {
    return (
      <div className="panel-empty compact-empty">
        <LoaderCircle className={path ? "spin" : ""} aria-hidden size={17} />
        <span>{path ? "학습 세션을 연결하고 있습니다." : "맞춤 학습 경로를 생성하고 있습니다."}</span>
      </div>
    );
  }

  const completed = new Set(session.completed_lesson_ids);
  const progress = session.total_lessons
    ? Math.round((session.completed_count / session.total_lessons) * 100)
    : 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuestion = question.trim();
    if (!nextQuestion || asking) return;
    setQuestion("");
    await onAsk(nextQuestion);
  }

  function toggleModule(moduleId: string) {
    setExpandedModules((currentValue) => {
      const next = new Set(currentValue);
      if (next.has(moduleId)) next.delete(moduleId);
      else next.add(moduleId);
      return next;
    });
  }

  return (
    <div className="journey-layout">
      <div className="journey-scroll" ref={scrollRef}>
        <section className="journey-overview">
          <div className="journey-kicker">
            <GraduationCap aria-hidden size={16} />
            <span>Adaptive Learning Journey</span>
            <button
              aria-label="학습 경로 다시 맞추기"
              disabled={busy}
              onClick={onReplan}
              title="현재 이해도로 학습 경로 다시 맞추기"
              type="button"
            >
              <RefreshCw className={busy ? "spin" : ""} aria-hidden size={13} />
            </button>
          </div>
          <h2>{path.title}</h2>
          <div className="journey-progress-copy">
            <span>
              {session.completed_count}/{session.total_lessons} 레슨
            </span>
            <small>
              <Clock3 aria-hidden size={12} /> 약 {path.estimated_minutes}분
            </small>
          </div>
          <div className="journey-progress-track" aria-label={`학습 진행률 ${progress}%`}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </section>

        {session.status === "completed" ? (
          <div className="journey-complete">
            <CheckCircle2 aria-hidden size={18} />
            <div>
              <strong>프로젝트 학습 경로 완료</strong>
              <span>각 레슨을 다시 열거나 코드 근거를 바탕으로 질문할 수 있습니다.</span>
            </div>
          </div>
        ) : null}

        <section className="journey-map">
          {path.modules.map((learningModule) => {
            const expanded =
              expandedModules.has(learningModule.id) ||
              learningModule.id === current.learningModule.id;
            const moduleCompleted = learningModule.lessons.filter((lesson) =>
              completed.has(lesson.id),
            ).length;
            return (
              <div className="journey-module" key={learningModule.id}>
                <button onClick={() => toggleModule(learningModule.id)} type="button">
                  {expanded ? <ChevronDown aria-hidden size={14} /> : <ChevronRight aria-hidden size={14} />}
                  <span>{learningModule.title}</span>
                  <small>
                    {moduleCompleted}/{learningModule.lessons.length}
                  </small>
                </button>
                {expanded ? (
                  <div className="journey-lessons">
                    {learningModule.lessons.map((lesson) => {
                      const isCurrent = lesson.id === session.current_lesson_id;
                      const isCompleted = completed.has(lesson.id);
                      return (
                        <button
                          className={`${isCurrent ? "is-current" : ""} ${isCompleted ? "is-completed" : ""}`}
                          key={lesson.id}
                          onClick={() => onOpenLesson(learningModule, lesson)}
                          type="button"
                        >
                          <span>{isCompleted ? <Check aria-hidden size={12} /> : lesson.ordinal}</span>
                          <div>
                            <strong>{lesson.title}</strong>
                            <small>{lesson.estimated_minutes}분</small>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </section>

        <section className="current-lesson">
          <div className="current-lesson-heading">
            <div>
              <small>{current.learningModule.title}</small>
              <h3>{current.lesson.title}</h3>
            </div>
            <span>{current.lesson.estimated_minutes}분</span>
          </div>
          <p>{current.lesson.objective}</p>
          {current.step ? <p className="lesson-instruction">{current.step.instruction}</p> : null}

          {current.step?.evidence ? (
            <button
              className="current-evidence"
              onClick={() => onOpenEvidence(current.step?.evidence as Citation)}
              title={current.step.evidence.path}
              type="button"
            >
              <FileCode2 aria-hidden size={14} />
              <span>{current.step.evidence.path}</span>
              <small>
                L{current.step.evidence.start_line}-{current.step.evidence.end_line}
              </small>
            </button>
          ) : null}

          {current.lesson.required_concept_ids.length ? (
            <div className="lesson-concepts">
              {current.lesson.required_concept_ids.map((concept) => (
                <span key={concept}>{concept.replaceAll("_", " ")}</span>
              ))}
            </div>
          ) : null}

          <div className="lesson-help-heading">
            <CircleHelp aria-hidden size={14} />
            <strong>막힌 부분 풀기</strong>
          </div>
          <div className="lesson-help-actions">
            {HELP_ACTIONS.map(({ mode, label, icon: Icon }) => (
              <button
                className={remediation?.mode === mode ? "is-active" : ""}
                disabled={busy}
                key={mode}
                onClick={() => onHelp(mode)}
                type="button"
              >
                {busy && remediation?.mode === mode ? (
                  <LoaderCircle className="spin" aria-hidden size={14} />
                ) : (
                  <Icon aria-hidden size={14} />
                )}
                {label}
              </button>
            ))}
          </div>

          {remediation ? (
            <RemediationContent
              branch={remediation}
              busy={busy}
              onComplete={onCompleteHelp}
              onOpenLines={onOpenLines}
            />
          ) : null}

          <CheckpointActivity
            activity={activity}
            attempt={activityAttempt}
            busy={activityBusy}
            onOpenEvidence={onOpenEvidence}
            onSubmit={onSubmitActivity}
          />

          <div className="lesson-checkpoint">
            <span>{current.lesson.checkpoint.prompt ?? "현재 흐름을 설명할 수 있나요?"}</span>
            <div>
              <button
                disabled={busy}
                onClick={() => onFeedback(current.lesson, "needs_help")}
                type="button"
              >
                <CircleHelp aria-hidden size={14} /> 아직 어려워요
              </button>
              <button
                className="lesson-understood"
                disabled={busy}
                onClick={() => onFeedback(current.lesson, "understood")}
                type="button"
              >
                {busy ? <LoaderCircle className="spin" aria-hidden size={14} /> : <Check size={14} />}
                이해했어요
              </button>
            </div>
          </div>
        </section>

        <section className="journey-chat">
          <div className="journey-chat-heading">
            <MessageSquareText aria-hidden size={15} />
            <strong>현재 레슨에 질문</strong>
          </div>
          {!answers.length ? (
            <div className="journey-prompts">
              {QUICK_QUESTIONS.map((prompt) => (
                <button key={prompt} onClick={() => setQuestion(prompt)} type="button">
                  <span>{prompt}</span>
                  <ChevronRight aria-hidden size={13} />
                </button>
              ))}
            </div>
          ) : null}
          {answers.map((item) => (
            <article className="answer-thread" key={item.id}>
              <div className="user-question">
                <MessageSquareText aria-hidden size={14} />
                <p>{item.question}</p>
              </div>
              <div className="grounded-answer">
                <div className="answer-meta">
                  <Sparkles aria-hidden size={14} />
                  <strong>RepoWise</strong>
                  <span>{item.status === "grounded" ? "근거 확인됨" : "근거 부족"}</span>
                </div>
                <p>{item.answer}</p>
              </div>
              {item.citations.length ? (
                <div className="citation-list">
                  {item.citations.map((citation) => (
                    <button
                      key={citation.evidence_id}
                      onClick={() => onOpenEvidence(citation)}
                      title={citation.preview}
                      type="button"
                    >
                      <Braces aria-hidden size={14} />
                      <span>{citation.path}</span>
                      <small>
                        L{citation.start_line}
                        {citation.end_line !== citation.start_line ? `-${citation.end_line}` : ""}
                      </small>
                    </button>
                  ))}
                </div>
              ) : null}
              {item.follow_up ? (
                <button className="follow-up-button" onClick={() => setQuestion(item.follow_up ?? "")} type="button">
                  {item.follow_up}
                  <ChevronRight aria-hidden size={14} />
                </button>
              ) : null}
            </article>
          ))}
          {asking ? (
            <div className="answer-loading">
              <LoaderCircle className="spin" aria-hidden size={17} />
              <span>현재 레슨과 코드 근거를 함께 확인 중</span>
            </div>
          ) : null}
        </section>
      </div>

      <form className="ask-composer journey-composer" onSubmit={submit}>
        <div className="teaching-level" aria-label="설명 깊이">
          {([
            ["beginner", "기초"],
            ["standard", "표준"],
            ["advanced", "심화"],
          ] as const).map(([style, label]) => (
            <button
              className={teachingStyle === style ? "is-active" : ""}
              key={style}
              onClick={() => onTeachingStyleChange(style)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
        <div className="journey-context-line">
          <GraduationCap aria-hidden size={13} />
          <span>{current.lesson.title}</span>
        </div>
        {selection && file ? (
          <div className="selection-context" title={file.path}>
            <Braces aria-hidden size={13} />
            <span>{file.path}</span>
            <small>
              L{selection.start_line}-{selection.end_line}
            </small>
          </div>
        ) : null}
        <div className="composer-row">
          <textarea
            aria-label="현재 레슨에 질문"
            disabled={asking}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="현재 코드에서 막힌 부분을 질문하세요"
            rows={2}
            value={question}
          />
          <button aria-label="질문 보내기" disabled={asking || !question.trim()} type="submit">
            {asking ? <LoaderCircle className="spin" size={16} /> : <Send aria-hidden size={16} />}
          </button>
        </div>
      </form>
    </div>
  );
}

function CheckpointActivity({
  activity,
  attempt,
  busy,
  onOpenEvidence,
  onSubmit,
}: {
  activity: LearningActivity | null;
  attempt: ActivityAttemptSummary | null;
  busy: boolean;
  onOpenEvidence: (citation: Citation) => void;
  onSubmit: (selectedChoiceId: string) => void;
}) {
  return (
    <div className="code-checkpoint">
      <div className="code-checkpoint-heading">
        <Target aria-hidden size={14} />
        <strong>코드로 이해 확인</strong>
      </div>
      {!activity ? (
        <div className="code-checkpoint-loading">
          <LoaderCircle className="spin" aria-hidden size={14} />
          <span>현재 코드에서 확인 문제를 준비 중입니다.</span>
        </div>
      ) : (
        <>
          <p>{activity.prompt}</p>
          <div className="checkpoint-choices">
            {activity.choices.map((choice) => (
              <button
                className={
                  attempt?.selected_choice_id === choice.id ? "is-selected" : ""
                }
                disabled={busy || Boolean(attempt)}
                key={choice.id}
                onClick={() => onSubmit(choice.id)}
                type="button"
              >
                <span>{choice.label}</span>
                {busy ? (
                  <LoaderCircle className="spin" aria-hidden size={13} />
                ) : (
                  <ChevronRight aria-hidden size={13} />
                )}
              </button>
            ))}
          </div>
          {attempt ? (
            <div
              className={`checkpoint-result ${attempt.is_correct ? "is-correct" : "is-incorrect"}`}
              role="status"
            >
              <div>
                {attempt.is_correct ? (
                  <CheckCircle2 aria-hidden size={15} />
                ) : (
                  <CircleHelp aria-hidden size={15} />
                )}
                <strong>
                  {attempt.feedback.message ??
                    (attempt.is_correct ? "정답입니다." : "코드 근거를 다시 확인하세요.")}
                </strong>
              </div>
              {attempt.feedback.explanation ? (
                <p>{attempt.feedback.explanation}</p>
              ) : null}
              {!attempt.is_correct && attempt.feedback.correct_label ? (
                <small>실제 근거: {attempt.feedback.correct_label}</small>
              ) : null}
              <button onClick={() => onOpenEvidence(activity.evidence)} type="button">
                <Braces aria-hidden size={13} /> 근거 코드 열기
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function findCurrent(path: LearningPath | null, session: LearningSession | null) {
  if (!path || !session) return null;
  for (const learningModule of path.modules) {
    const lesson = learningModule.lessons.find(
      (item) => item.id === session.current_lesson_id,
    );
    if (lesson) {
      return {
        learningModule,
        lesson,
        step: lesson.steps[0] ?? null,
      };
    }
  }
  return null;
}

function RemediationContent({
  branch,
  busy,
  onComplete,
  onOpenLines,
}: {
  branch: RemediationBranch;
  busy: boolean;
  onComplete: () => void;
  onOpenLines: (fileId: string, startLine: number, endLine: number) => void;
}) {
  const content = branch.content;
  return (
    <div className="remediation-panel">
      {content.segments?.map((segment) => (
        <button
          className="explanation-segment"
          key={segment.segment_id}
          onClick={() =>
            content.file_id && onOpenLines(content.file_id, segment.start_line, segment.end_line)
          }
          type="button"
        >
          <code>{segment.source}</code>
          <span>{segment.what}</span>
          <small>{segment.why}</small>
        </button>
      ))}
      {content.concepts?.map((concept) => (
        <div className="concept-bridge" key={concept.concept_id}>
          <strong>{concept.title}</strong>
          {content.gap_resolution?.find(
            (item) => item.concept_id === concept.concept_id,
          ) ? (
            <span className="concept-gap-reason">
              {
                content.gap_resolution.find(
                  (item) => item.concept_id === concept.concept_id,
                )?.rationale
              }
            </span>
          ) : null}
          <p>{concept.definition}</p>
          <small>{concept.check_question}</small>
        </div>
      ))}
      {content.examples?.map((example) => (
        <div className="small-example" key={example.concept_id}>
          <strong>{example.concept_id.replaceAll("_", " ")}</strong>
          <pre>{example.code}</pre>
        </div>
      ))}
      {content.sources?.map((source) => (
        <a href={source.canonical_url} key={source.id} rel="noreferrer" target="_blank">
          <BookOpenCheck aria-hidden size={14} />
          <span>
            <strong>{source.title}</strong>
            <small>
              {source.publisher} · {source.estimated_minutes}분
            </small>
          </span>
          <ExternalLink aria-hidden size={13} />
        </a>
      ))}
      <button className="remediation-return" disabled={busy} onClick={onComplete} type="button">
        <RotateCcw aria-hidden size={14} /> 원래 레슨으로 돌아가기
      </button>
    </div>
  );
}
