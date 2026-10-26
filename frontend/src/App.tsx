import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";

type ContextTab = "doc" | "files" | "eval";
interface DeleteTarget {
  id: string;
  name: string;
}

export default function App() {
  const [projects, setProjects] = useState<api.ProjectSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<api.ProjectDetail | null>(null);
  const [tab, setTab] = useState<ContextTab>("doc");
  const [name, setName] = useState("");
  const [requirement, setRequirement] = useState("");
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<api.FileItem[]>([]);
  const [diff, setDiff] = useState("");
  const [evaluation, setEvaluation] = useState<api.Evaluation | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteTraces, setDeleteTraces] = useState(false);
  const [deleteExport, setDeleteExport] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const sourceRef = useRef<EventSource | null>(null);

  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(String(err));
    }
  }, []);

  const refreshDetail = useCallback(async (id: string) => {
    try {
      setDetail(await api.getProject(id));
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    refreshDetail(selected);
    const timer = window.setInterval(() => refreshDetail(selected), 2500);
    return () => window.clearInterval(timer);
  }, [selected, refreshDetail]);

  useEffect(() => {
    if (!selected) return;
    if (tab === "files") {
      api.listFiles(selected).then(setFiles).catch((err) => setError(String(err)));
    }
    if (tab === "eval") {
      api.getEvaluation(selected).then(setEvaluation).catch((err) => setError(String(err)));
    }
  }, [tab, selected]);

  useEffect(() => {
    if (!detail?.run_id) return;
    sourceRef.current?.close();
    const source = new EventSource(`/api/runs/${detail.run_id}/events/stream`);
    source.onmessage = () => {
      if (selected) refreshDetail(selected);
    };
    source.onerror = () => source.close();
    sourceRef.current = source;
    return () => source.close();
  }, [detail?.run_id, selected, refreshDetail]);

  const lastMessage = detail?.messages[detail.messages.length - 1];
  const pendingQuestions = questionsFromMessage(lastMessage);
  const lastMessageId = lastMessage?.id;

  useEffect(() => {
    if (!pendingQuestions.length) {
      setAnswers({});
      return;
    }
    const next: Record<number, string> = {};
    pendingQuestions.forEach((question, index) => {
      next[index] = question.recommendation ?? "";
    });
    setAnswers(next);
  }, [lastMessageId]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const createProject = () =>
    run(async () => {
      if (!name.trim()) {
        setError("请填写项目名称");
        return;
      }
      const created = await api.createProject(name.trim(), requirement.trim());
      setName("");
      setRequirement("");
      await refreshProjects();
      setSelected(created.project_id);
      await api.startAlignment(created.project_id);
      await refreshDetail(created.project_id);
    });

  const startAlignment = () =>
    run(async () => {
      if (!selected) return;
      await api.startAlignment(selected);
      await refreshDetail(selected);
    });

  const send = () =>
    run(async () => {
      if (!selected || !text.trim()) return;
      const result = await api.sendMessage(selected, text.trim());
      if ((result as { action?: string }).action === "review") setTab("doc");
      setText("");
      await refreshDetail(selected);
    });

  const submitAnswers = () =>
    run(async () => {
      if (!selected || !pendingQuestions.length) return;
      const entries = pendingQuestions.map((question, index) => ({
        question: question.question,
        answer: (answers[index] ?? "").trim()
      }));
      if (entries.some((entry) => !entry.answer)) {
        setError("请为每个问题填写回答，或点“采用推荐”。");
        return;
      }
      const body =
        "本轮回答：\n" +
        entries
          .map((entry, index) => `${index + 1}. ${entry.question}\n回答：${entry.answer}`)
          .join("\n\n");
      const result = await api.sendMessage(selected, body);
      if ((result as { action?: string }).action === "review") setTab("doc");
      await refreshDetail(selected);
    });

  const approve = () =>
    run(async () => {
      if (!selected || !detail?.readme) return;
      await api.approveDocument(selected, detail.readme.id);
      setTab("doc");
      await refreshDetail(selected);
    });

  const change = () =>
    run(async () => {
      if (!selected || !detail?.readme || !feedback.trim()) return;
      await api.requestChanges(selected, detail.readme.id, feedback.trim());
      setFeedback("");
      await refreshDetail(selected);
    });

  const loadDiff = () =>
    run(async () => {
      if (!selected) return;
      setDiff((await api.getDiff(selected)).diff);
    });

  const refreshFiles = () =>
    run(async () => {
      if (!selected) return;
      setFiles(await api.listFiles(selected));
    });

  const refreshEvaluation = () =>
    run(async () => {
      if (!selected) return;
      setEvaluation(await api.getEvaluation(selected));
    });

  const togglePreview = () =>
    run(async () => {
      if (!selected) return;
      if (previewUrl) {
        await api.stopPreview(selected);
        setPreviewUrl("");
      } else {
        const session = await api.startPreview(selected);
        setPreviewUrl(session.url);
      }
    });

  const setStatus = (action: "pause" | "resume" | "cancel") =>
    run(async () => {
      if (!selected) return;
      if (action === "pause") await api.pauseProject(selected);
      if (action === "resume") await api.resumeProject(selected);
      if (action === "cancel") await api.cancelProject(selected);
      await refreshDetail(selected);
    });

  const openDelete = (target: DeleteTarget) => {
    setDeleteTarget(target);
    setDeleteTraces(false);
    setDeleteExport(false);
    setDeleteError("");
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setDeleteError("");
    try {
      if (deleteExport) {
        const response = await fetch(api.downloadUrl(deleteTarget.id));
        if (!response.ok) {
          throw new Error("导出源码失败，项目未删除");
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${deleteTarget.name}.zip`;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      await api.deleteProject(deleteTarget.id, !deleteTraces, false);
      if (selected === deleteTarget.id) {
        setSelected(null);
        setDetail(null);
      }
      setDeleteTarget(null);
      await refreshProjects();
    } catch (err) {
      setDeleteError(String(err));
    } finally {
      setDeleteBusy(false);
    }
  };

  const status = detail?.run_status ?? detail?.status ?? "";
  const readme = detail?.readme ?? null;
  const hasPlannerMessage = Boolean(
    detail?.messages.some((message) => message.role !== "user")
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">A</span>
          <div>
            <strong>autoagent</strong>
            <small>需求到可运行源码</small>
          </div>
        </div>

        <div className="new-project">
          <input
            placeholder="项目名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <textarea
            placeholder="一句话说出你的需求"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
          />
          <button className="btn primary" disabled={busy} onClick={createProject}>
            新建项目
          </button>
        </div>

        <div className="sidebar-section">
          <span>项目</span>
          <span className="count">{projects.length}</span>
        </div>

        <div className="project-list">
          {projects.map((project) => (
            <div
              key={project.id}
              className={`project-row ${selected === project.id ? "active" : ""}`}
              onClick={() => setSelected(project.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter") setSelected(project.id);
              }}
            >
              <div className="project-main">
                <span className="project-name">{project.name}</span>
                <span className="project-status">{project.status}</span>
              </div>
              <button
                className="icon-btn"
                aria-label="删除此项目"
                title="删除此项目"
                onClick={(event) => {
                  event.stopPropagation();
                  openDelete(project);
                }}
              >
                ×
              </button>
            </div>
          ))}
          {projects.length === 0 && <p className="empty-hint">还没有项目</p>}
        </div>
      </aside>

      <main className="main">
        {!detail ? (
          <section className="welcome">
            <div className="welcome-mark">A</div>
            <h1>把一句话变成能运行的软件</h1>
            <p>
              左侧新建项目，先回答几个通俗的问题；确认需求文档后，系统会拆计划、写代码、跑测试并交付可启动的源码。
            </p>
          </section>
        ) : (
          <>
            <header className="topbar">
              <div className="title-block">
                <div className="crumbs">项目 / {detail.name}</div>
                <div className="title-line">
                  <h1>{detail.name}</h1>
                  <StatusPill status={status} />
                </div>
              </div>
              <div className="top-actions">
                <a className="btn ghost" href={api.downloadUrl(detail.id)}>
                  下载源码
                </a>
                <button className="btn ghost" disabled={busy} onClick={() => setStatus("pause")}>
                  暂停
                </button>
                <button className="btn ghost" disabled={busy} onClick={() => setStatus("resume")}>
                  继续
                </button>
                <button className="btn ghost danger-text" disabled={busy} onClick={() => setStatus("cancel")}>
                  取消
                </button>
                <button
                  className="btn ghost danger-text"
                  disabled={busy}
                  onClick={() => openDelete({ id: detail.id, name: detail.name })}
                >
                  删除项目
                </button>
              </div>
            </header>

            {error && <div className="error-bar">{error}</div>}

            <div className="workbench">
              <section className="conversation">
                <div className="messages">
                  {detail.messages.map((message, index) => (
                    <div
                      key={message.id}
                      className={`message ${message.role === "user" ? "user" : "agent"}`}
                    >
                      <div className="message-avatar">
                        {message.role === "user" ? "你" : "A"}
                      </div>
                      <div className="message-body">
                        <div className="message-meta">
                          {message.role === "user" ? "你" : message.agent_id ?? "autoagent"}
                        </div>
                        {index === detail.messages.length - 1 &&
                        message.role !== "user" &&
                        pendingQuestions.length > 0 ? (
                          <QuestionBatch
                            questions={pendingQuestions}
                            answers={answers}
                            busy={busy}
                            onChange={(questionIndex, value) =>
                              setAnswers((current) => ({
                                ...current,
                                [questionIndex]: value
                              }))
                            }
                            onUseRecommendation={(questionIndex) =>
                              setAnswers((current) => ({
                                ...current,
                                [questionIndex]:
                                  pendingQuestions[questionIndex].recommendation ?? ""
                              }))
                            }
                            onSubmit={submitAnswers}
                          />
                        ) : (
                          <div className="message-content">{message.content}</div>
                        )}
                      </div>
                    </div>
                  ))}
                  {detail.messages.length === 0 && (
                    <div className="conversation-empty">
                      <p>从一个问题开始，或者说出你的想法。</p>
                    </div>
                  )}
                  {status === "对齐中" && !hasPlannerMessage && (
                    <button className="btn primary inline" disabled={busy} onClick={startAlignment}>
                      开始需求对齐
                    </button>
                  )}
                </div>

                <div className="composer">
                  <textarea
                    placeholder="回答问题，或输入“够了”开始生成需求文档"
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) send();
                    }}
                  />
                  <div className="composer-bar">
                    <span className="hint">Ctrl + Enter 发送</span>
                    <button className="btn primary" disabled={busy} onClick={send}>
                      发送
                    </button>
                  </div>
                </div>
              </section>

              <aside className="context">
                <nav className="context-tabs">
                  {(
                    [
                      ["doc", "需求文档"],
                      ["files", "文件与预览"],
                      ["eval", "评测"]
                    ] as Array<[ContextTab, string]>
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      className={tab === key ? "active" : ""}
                      onClick={() => setTab(key)}
                    >
                      {label}
                    </button>
                  ))}
                </nav>

                <div className="context-body">
                  {tab === "doc" &&
                    (readme ? (
                      <div className="doc-view">
                        <div className="doc-meta">
                          <span>第 {readme.version} 版</span>
                          <span className={`pill ${readme.status === "approved" ? "ok" : "warn"}`}>
                            {readme.status === "approved" ? "已通过" : "待审阅"}
                          </span>
                        </div>
                        <pre className="doc-content">{readme.content}</pre>
                        <div className="row">
                          <button
                            className="btn primary"
                            disabled={busy || readme.status === "approved"}
                            onClick={approve}
                          >
                            通过并开始生成
                          </button>
                          <button className="btn ghost" disabled={busy} onClick={loadDiff}>
                            版本差异
                          </button>
                        </div>
                        <textarea
                          className="feedback"
                          placeholder="把修改意见写在这里"
                          value={feedback}
                          onChange={(event) => setFeedback(event.target.value)}
                        />
                        <button className="btn ghost" disabled={busy} onClick={change}>
                          提交修改意见
                        </button>
                        {diff && <pre className="diff">{diff}</pre>}
                      </div>
                    ) : (
                      <p className="muted">
                        还没有需求文档。先在左侧对话里完成需求对齐，再到这里审阅。
                      </p>
                    ))}

                  {tab === "files" && (
                    <div className="files-view">
                      <div className="row">
                        <button className="btn ghost" disabled={busy} onClick={refreshFiles}>
                          刷新文件
                        </button>
                        <button className="btn primary" disabled={busy} onClick={togglePreview}>
                          {previewUrl ? "停止预览" : "启动预览"}
                        </button>
                        {previewUrl && (
                          <a className="btn ghost" href={previewUrl} target="_blank" rel="noreferrer">
                            打开预览
                          </a>
                        )}
                      </div>
                      <ul className="file-list">
                        {files.map((file) => (
                          <li key={file.path}>
                            <span>{file.path}</span>
                            <small>{Math.ceil(file.size / 1024)} KB</small>
                          </li>
                        ))}
                        {files.length === 0 && <li className="muted">暂无文件</li>}
                      </ul>
                      <div className="sidebar-section compact">
                        <span>模块</span>
                      </div>
                      <ul className="module-list">
                        {detail.modules.map((module) => (
                          <li key={module.id}>
                            <span>{module.name}</span>
                            <small>{module.status}</small>
                          </li>
                        ))}
                        {detail.modules.length === 0 && <li className="muted">暂无模块</li>}
                      </ul>
                    </div>
                  )}

                  {tab === "eval" && (
                    <div className="eval-view">
                      <button className="btn ghost" disabled={busy} onClick={refreshEvaluation}>
                        刷新评测
                      </button>
                      {evaluation ? (
                        <>
                          <div className="metric-grid">
                            {Object.entries(evaluation.metrics)
                              .filter(([, value]) => typeof value !== "object")
                              .map(([key, value]) => (
                                <div className="metric" key={key}>
                                  <small>{key}</small>
                                  <strong>{String(value)}</strong>
                                </div>
                              ))}
                          </div>
                          <table className="score-table">
                            <thead>
                              <tr>
                                <th>维度</th>
                                <th>分数</th>
                                <th>判定</th>
                                <th>证据</th>
                              </tr>
                            </thead>
                            <tbody>
                              {evaluation.scores.map((row) => (
                                <tr key={`${row.dimension}-${row.judge}`}>
                                  <td>{row.dimension}</td>
                                  <td>{row.score}</td>
                                  <td>{row.judge}</td>
                                  <td>{row.evidence.join("，") || "无"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {evaluation.scores.length === 0 && (
                            <p className="muted">评测尚未生成。</p>
                          )}
                        </>
                      ) : (
                        <p className="muted">点击刷新，查看本次运行的全量数据。</p>
                      )}
                    </div>
                  )}
                </div>
              </aside>
            </div>
          </>
        )}
      </main>

      {deleteTarget && (
        <DeleteDialog
          target={deleteTarget}
          deleteTraces={deleteTraces}
          setDeleteTraces={setDeleteTraces}
          deleteExport={deleteExport}
          setDeleteExport={setDeleteExport}
          busy={deleteBusy}
          error={deleteError}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}

function questionsFromMessage(message: api.Message | undefined): api.Question[] {
  if (!message || message.role === "user") return [];
  const list = message.meta?.questions?.questions;
  return Array.isArray(list) ? list : [];
}

function QuestionBatch({
  questions,
  answers,
  busy,
  onChange,
  onUseRecommendation,
  onSubmit
}: {
  questions: api.Question[];
  answers: Record<number, string>;
  busy: boolean;
  onChange: (index: number, value: string) => void;
  onUseRecommendation: (index: number) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="question-batch">
      <div className="question-batch-head">请逐题确认 · 共 {questions.length} 个问题</div>
      {questions.map((question, index) => (
        <div className="question-card" key={`${index}-${question.question}`}>
          <div className="question-head">
            <span className="question-index">{index + 1}</span>
            <span>{question.question}</span>
          </div>
          {question.reason && <p className="question-reason">推荐理由：{question.reason}</p>}
          <div className="question-recommend">
            <span className="question-label">推荐做法</span>
            <span>{question.recommendation || "暂无推荐，请自行填写"}</span>
            {question.recommendation && (
              <button
                className="btn ghost small"
                disabled={busy}
                onClick={() => onUseRecommendation(index)}
              >
                采用推荐
              </button>
            )}
          </div>
          <textarea
            className="question-input"
            value={answers[index] ?? ""}
            onChange={(event) => onChange(index, event.target.value)}
            placeholder="可以采用推荐做法，也可以在这里写你自己的答案"
          />
        </div>
      ))}
      <div className="question-actions">
        <span className="hint">每题都可以单独修改；也可以直接说“够了”。</span>
        <button className="btn primary" disabled={busy} onClick={onSubmit}>
          提交本轮回答
        </button>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "已交付"
      ? "ok"
      : status === "失败" || status === "取消"
        ? "bad"
        : status === "暂停"
          ? "warn"
          : "run";
  return <span className={`pill ${cls}`}>{status || "—"}</span>;
}

function DeleteDialog({
  target,
  deleteTraces,
  setDeleteTraces,
  deleteExport,
  setDeleteExport,
  busy,
  error,
  onCancel,
  onConfirm
}: {
  target: DeleteTarget;
  deleteTraces: boolean;
  setDeleteTraces: (value: boolean) => void;
  deleteExport: boolean;
  setDeleteExport: (value: boolean) => void;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-overlay" role="presentation" onClick={onCancel}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="delete-title">删除项目</h2>
        <p>
          确定删除「{target.name}」吗？生成物、项目记忆与工作区会被移除，操作不可撤销。
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={deleteTraces}
            onChange={(event) => setDeleteTraces(event.target.checked)}
          />
          彻底删除（同时删除匿名运行轨迹）
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={deleteExport}
            onChange={(event) => setDeleteExport(event.target.checked)}
          />
          删除前导出源码
        </label>
        {error && <div className="modal-error">{error}</div>}
        <div className="modal-actions">
          <button className="btn ghost" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="btn danger" onClick={onConfirm} disabled={busy}>
            {busy ? "删除中…" : "确认删除"}
          </button>
        </div>
      </div>
    </div>
  );
}
