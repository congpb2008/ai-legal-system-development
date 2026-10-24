import type {
  AdminSettings,
  AdminStats,
  AdminUser,
  AuditEvent,
  DocumentRecord,
  Job,
  LegalNode,
  PageRecord,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg?: string }) => item.msg).join("; ");
    } catch {
      // keep status text
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  async me(): Promise<User | null> {
    return request<User | null>("/api/auth/optional");
  },

  login(email: string, password: string): Promise<{ user: User }> {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  register(email: string, password: string): Promise<{ user: User }> {
    return request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  logout(): Promise<{ ok: boolean }> {
    return request("/api/auth/logout", { method: "POST" });
  },

  documents(): Promise<DocumentRecord[]> {
    return request("/api/documents");
  },

  document(id: string): Promise<DocumentRecord> {
    return request(`/api/documents/${id}`);
  },

  uploadDocument(file: File): Promise<DocumentRecord> {
    const body = new FormData();
    body.append("file", file);
    return request("/api/documents/upload", { method: "POST", body });
  },

  deleteDocument(id: string): Promise<{ ok: boolean }> {
    return request(`/api/documents/${id}`, { method: "DELETE" });
  },

  documentTree(id: string): Promise<LegalNode[]> {
    return request(`/api/documents/${id}/tree`);
  },

  documentPages(id: string): Promise<PageRecord[]> {
    return request(`/api/documents/${id}/pages`);
  },

  search(query: string, documentIds?: string[]): Promise<SearchResult[]> {
    return request("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: 8, document_ids: documentIds }),
    });
  },

  chat(
    message: string,
    history: Array<{ role: "user" | "assistant"; content: string }> = [],
    documentIds?: string[],
    generateAnswer = true,
  ): Promise<ChatResponse> {
    return request("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        history,
        top_k: 8,
        generate_answer: generateAnswer,
        document_ids: documentIds,
      }),
    });
  },

  streamChat(
    message: string,
    history: Array<{ role: "user" | "assistant"; content: string }> = [],
    documentIds?: string[],
    generateAnswer = true,
  ): Promise<Response> {
    return fetch("/api/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history,
        top_k: 8,
        generate_answer: generateAnswer,
        document_ids: documentIds,
      }),
    });
  },

  adminStats(): Promise<AdminStats> {
    return request("/api/admin/stats");
  },

  adminUsers(): Promise<AdminUser[]> {
    return request("/api/admin/users");
  },

  adminAudit(): Promise<AuditEvent[]> {
    return request("/api/admin/audit");
  },

  updateUser(userId: string, patch: { role?: "user" | "admin"; is_active?: boolean }): Promise<AdminUser> {
    return request(`/api/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  reindexDocument(documentId: string): Promise<{ ok: boolean; job_id: string }> {
    return request(`/api/admin/documents/${documentId}/reindex`, { method: "POST" });
  },

  updateLegalNode(
    nodeId: string,
    patch: { title?: string; text?: string },
  ): Promise<{ ok: boolean; document_id: string }> {
    return request(`/api/admin/legal-nodes/${nodeId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  adminSettings(): Promise<AdminSettings> {
    return request("/api/admin/settings");
  },

  updateAdminSettings(payload: {
    llm?: Partial<{
      base_url: string | null;
      api_key: string | null;
      api_key_clear: boolean;
      model: string | null;
      timeout_seconds: number | null;
      enabled: boolean | null;
    }>;
    embeddings?: Partial<{
      provider: "hash" | "openai" | null;
      base_url: string | null;
      api_key: string | null;
      api_key_clear: boolean;
      model: string | null;
      dim: number | null;
    }>;
  }): Promise<AdminSettings> {
    return request("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  testLLM(): Promise<{ ok: boolean; message?: string; error?: string }> {
    return request("/api/admin/settings/test/llm", { method: "POST" });
  },

  testEmbeddings(): Promise<{ ok: boolean; message?: string; error?: string }> {
    return request("/api/admin/settings/test/embeddings", { method: "POST" });
  },
};

import type { ChatResponse, SearchResult } from "./types";
