export interface ProjectSummary {
  id: string;
  name: string;
  status: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: string;
  agent_id: string | null;
  content: string;
  created_at: string;
}

export interface Readme {
  id: string;
  version: number;
  status: string;
  content: string;
}

export interface ModuleInfo {
  id: string;
  name: string;
  status: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  status: string;
  run_id: string | null;
  run_status: string | null;
  messages: Message[];
  readme: Readme | null;
  modules: ModuleInfo[];
}

export interface FileItem {
  path: string;
  size: number;
}

export interface Evaluation {
  run_id: string;
  metrics: Record<string, unknown>;
  scores: Array<{
    dimension: string;
    score: number;
    evidence: string[];
    judge: string;
  }>;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText || `HTTP ${response.status}`;
    try {
      const data = JSON.parse(text) as { detail?: unknown };
      if (typeof data.detail === "string" && data.detail) {
        message = data.detail;
      }
    } catch {
      // 保留原始文本
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const listProjects = () => request<ProjectSummary[]>("/api/projects");

export const createProject = (name: string, requirement: string) =>
  request<{ project_id: string; run_id: string; status: string }>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, requirement })
  });

export const getProject = (id: string) =>
  request<ProjectDetail>(`/api/projects/${id}`);

export const startAlignment = (id: string) =>
  request<{ run_id: string; questions: { questions: unknown[] } }>(
    `/api/projects/${id}/align`,
    { method: "POST" }
  );

export const sendMessage = (id: string, text: string) =>
  request<Record<string, unknown>>(`/api/projects/${id}/messages`, {
    method: "POST",
    body: JSON.stringify({ text })
  });

export const approveDocument = (projectId: string, documentId: string) =>
  request<Record<string, unknown>>(
    `/api/projects/${projectId}/documents/${documentId}/approve`,
    { method: "POST" }
  );

export const requestChanges = (
  projectId: string,
  documentId: string,
  feedback: string
) =>
  request<Record<string, unknown>>(
    `/api/projects/${projectId}/documents/${documentId}/changes`,
    { method: "POST", body: JSON.stringify({ feedback }) }
  );

export const getDiff = (projectId: string) =>
  request<{ diff: string }>(`/api/projects/${projectId}/documents/diff`);

export const listFiles = (projectId: string) =>
  request<FileItem[]>(`/api/projects/${projectId}/files`);

export const startPreview = (projectId: string) =>
  request<{ url: string; port: number }>(
    `/api/projects/${projectId}/preview/start`,
    { method: "POST" }
  );

export const stopPreview = (projectId: string) =>
  request<{ stopped: boolean }>(`/api/projects/${projectId}/preview/stop`, {
    method: "POST"
  });

export const pauseProject = (projectId: string) =>
  request<Record<string, unknown>>(`/api/projects/${projectId}/pause`, {
    method: "POST"
  });

export const resumeProject = (projectId: string) =>
  request<Record<string, unknown>>(`/api/projects/${projectId}/resume`, {
    method: "POST"
  });

export const cancelProject = (projectId: string) =>
  request<Record<string, unknown>>(`/api/projects/${projectId}/cancel`, {
    method: "POST"
  });

export const getEvaluation = (projectId: string) =>
  request<Evaluation>(`/api/projects/${projectId}/evaluation`);

export const downloadUrl = (projectId: string) =>
  `/api/projects/${projectId}/download`;
