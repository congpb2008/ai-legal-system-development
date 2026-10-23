import type {
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

  jobs(id: string): Promise<Job[]> {
    return request(`/api/documents/${id}/jobs`);
  },

  nodes(id: string): Promise<LegalNode[]> {
    return request(`/api/documents/${id}/nodes`);
  },

  pageText(id: string, page: number): Promise<PageRecord> {
    return request(`/api/documents/${id}/pages/${page}`);
  },

  adminStats(): Promise<AdminStats> {
    return request("/api/admin/stats");
  },

  adminUsers(): Promise<AdminUser[]> {
    return request("/api/admin/users");
  },

  updateUser(id: string, patch: { role?: "user" | "admin"; is_active?: boolean }): Promise<AdminUser> {
    return request(`/api/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  adminAudit(): Promise<AuditEvent[]> {
    return request("/api/admin/audit?limit=200");
  },

  reindexDocument(id: string): Promise<{ ok: boolean; job_id: string }> {
    return request(`/api/admin/documents/${id}/reindex`, { method: "POST" });
  },

  documentFileUrl(id: string): string {
    return `/api/documents/${id}/file`;
  },
};
