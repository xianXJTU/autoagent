import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";

type Tab = "chat" | "doc" | "files" | "eval";

export default function App() {
  const [projects, setProjects] = useState<api.ProjectSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<api.ProjectDetail | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
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
  const sourceRef = useRef<EventSource | null>(null);

  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(String(err));
    }
  }, []);

  const refreshDetail = useCallback(
    async (id: string) => {
      try {
        const data = await api.getProject(id);
        setDetail(data);
        if (tab === "files") setFiles(await api.listFiles(id));
        if (tab === "eval") setEvaluation(await api.getEvaluation(id));
      } catch (err) {
        setError(String(err));
      }
    },
    [tab]
  );

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    if (!selected) return;
    refreshDetail(selected);
    const timer = window.setInterval(() => refreshDetail(selected), 2500);
    return () => window.clearInterval(timer);
  }, [selected, refreshDetail]);

  useEffect(() => {
    if (!detail?.run_id) return;
    sourceRef.current?.close();
    const source = new EventSource(
      `/api/runs/${detail.run_id}/events/stream`
    );
    source.onmessage = () => {
      if (selected) refreshDetail(selected);
    };
    source.onerror = () => source.close();
    sourceRef.current = source;
    return () => source.close();
  }, [detail?.run_id, selected, refreshDetail]);

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

  const send = () =>
    run(async () => {
      if (!selected || !text.trim()) return;
      await api.sendMessage(selected, text.trim());
      setText("");
      await refreshDetail(selected);
    });

  const approve = () =>
    run(async () => {
      if (!selected || !detail?.readme) return;
      await api.approveDocument(selected, detail.readme.id);
      setTab("chat");
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

  const status = detail?.run_status ?? detail?.status ?? "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="dot" />
          autoagent
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
          <button disabled={busy} onClick={createProject}>
            新建项目
          </button>
        </div>
        <div className="project-list">
          {projects.map((project) => (
            <button
              key={project.id}
              className={`project-item ${selected === project.id ? "active" : ""}`}
              onClick={() => setSelected(project.id)}
            >
              <span>{project.name}</span>
              <small>{project.status}</small>
            </button>
          ))}
        </div>
      </aside>

      <main className="main">
        {!detail ? (
          <section className="welcome">
            <h1>把一句话变成能运行的软件</h1>
            <p>左侧新建项目，系统会先追问需求，再生成可审阅的文档，最后交付源码。</p>
          </section>
        ) : (
          <>
            <header className="topbar">
              <div>
                <h2>{detail.name}</h2>
                <span className={`status ${statusClass(status)}`}>{status}</span>
              </div>
              <div className="actions">
                <a className="ghost" href={api.downloadUrl(detail.id)}>
                  下载源码
                </a>
                <button className="ghost" disabled={busy} onClick={() => run(async () => {
                  if (!selected) return;
                  await api.pauseProject(selected);
                  await refreshDetail(selected);
                })}>
                  暂停
                </button>
                <button className="ghost" disabled={busy} onClick={() => run(async () => {
                  if (!selected) return;
                  await api.resumeProject(selected);
                  await refreshDetail(selected);
                })}>
                  继续
                </button>
                <button className="danger" disabled={busy} onClick={() => run(async () => {
                  if (!selected) return;
                  await api.cancelProject(selected);
                  await refreshDetail(selected);
                })}>
                  取消
                </button>
              </div>
            </header>

            <nav className="tabs">
              {(
                [
                  ["chat", "对话"],
                  ["doc", "需求文档"],
                  ["files", "文件与预览"],
                  ["eval", "评测"]
                ] as Array<[Tab, string]>
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

            {error && <div className="error">{error}</div>}

            {tab === "chat" && (
              <section className="panel chat-panel">
                <div className="messages">
                  {detail.messages.map((message) => (
                    <div
                      key={message.id}
                      className={`message ${message.role === "user" ? "user" : "agent"}`}
                    >
                      <div className="meta">
                        {message.role === "user" ? "你" : message.agent_id ?? "代理"}
                      </div>
                      <div className="content">{message.content}</div>
                    </div>
                  ))}
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
                  <button disabled={busy} onClick={send}>
                    发送
                  </button>
                </div>
              </section>
            )}

            {tab === "doc" && (
              <section className="panel doc-panel">
                {detail.readme ? (
                  <>
                    <div className="doc-head">
                      <span>第 {detail.readme.version} 版</span>
                      <span>{detail.readme.status === "approved" ? "已通过" : "待审阅"}</span>
                    </div>
                    <pre>{detail.readme.content}</pre>
                    <div className="row">
                      <button disabled={busy || detail.readme.status === "approved"} onClick={approve}>
                        通过并开始生成
                      </button>
                      <button className="ghost" disabled={busy} onClick={loadDiff}>
                        查看版本差异
                      </button>
                    </div>
                    <textarea
                      placeholder="提出修改意见"
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                    />
                    <button className="ghost" disabled={busy} onClick={change}>
                      提交修改意见
                    </button>
                    {diff && <pre className="diff">{diff}</pre>}
                  </>
                ) : (
                  <p className="muted">还没有需求文档，请先在对话里完成对齐。</p>
                )}
              </section>
            )}

            {tab === "files" && (
              <section className="panel files-panel">
                <div className="row">
                  <button className="ghost" disabled={busy} onClick={() => run(async () => {
                    if (!selected) return;
                    setFiles(await api.listFiles(selected));
                  })}>
                    刷新文件
                  </button>
                  <button disabled={busy} onClick={togglePreview}>
                    {previewUrl ? "停止预览" : "启动预览"}
                  </button>
                  {previewUrl && (
                    <a className="ghost" href={previewUrl} target="_blank" rel="noreferrer">
                      打开 {previewUrl}
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
                <ul className="module-list">
                  {detail.modules.map((module) => (
                    <li key={module.id}>
                      <span>{module.name}</span>
                      <small>{module.status}</small>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {tab === "eval" && (
              <section className="panel eval-panel">
                <button className="ghost" disabled={busy} onClick={() => run(async () => {
                  if (!selected) return;
                  setEvaluation(await api.getEvaluation(selected));
                })}>
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
                  <p className="muted">点击刷新查看本次运行的全量数据。</p>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function statusClass(status: string): string {
  if (status === "已交付") return "ok";
  if (status === "失败" || status === "取消") return "bad";
  if (status === "暂停") return "warn";
  return "run";
}
