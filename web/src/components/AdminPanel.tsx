import { useEffect, useState } from "react";
import { Activity, Database, FileText, Loader2, ScrollText, Settings, ShieldCheck, Users, X } from "lucide-react";
import { api } from "../api";
import type { AdminSettings, AdminStats, AdminUser, AuditEvent } from "../types";

type Props = {
  onClose: () => void;
};

type Tab = "overview" | "users" | "audit" | "settings";

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

export function AdminPanel({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingLLM, setTestingLLM] = useState(false);
  const [testingEmb, setTestingEmb] = useState(false);
  const [llmForm, setLlmForm] = useState({
    base_url: "",
    api_key: "",
    api_key_clear: false,
    model: "gpt-4o-mini",
    timeout_seconds: 300,
    enabled: true,
  });
  const [embForm, setEmbForm] = useState({
    provider: "hash" as "hash" | "openai",
    base_url: "",
    api_key: "",
    api_key_clear: false,
    model: "text-embedding-3-small",
    dim: 384,
  });

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [nextStats, nextUsers, nextAudit, nextSettings] = await Promise.all([
        api.adminStats(),
        api.adminUsers(),
        api.adminAudit(),
        api.adminSettings(),
      ]);
      setStats(nextStats);
      setUsers(nextUsers);
      setAudit(nextAudit);
      setSettings(nextSettings);
      setLlmForm({
        base_url: nextSettings.llm.base_url || "",
        api_key: "",
        api_key_clear: false,
        model: nextSettings.llm.model || "gpt-4o-mini",
        timeout_seconds: nextSettings.llm.timeout_seconds || 300,
        enabled: nextSettings.llm.enabled,
      });
      setEmbForm({
        provider: nextSettings.embeddings.provider || "hash",
        base_url: nextSettings.embeddings.base_url || "",
        api_key: "",
        api_key_clear: false,
        model: nextSettings.embeddings.model || "text-embedding-3-small",
        dim: nextSettings.embeddings.dim || 384,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu quản trị.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function updateUser(user: AdminUser, patch: { role?: "user" | "admin"; is_active?: boolean }) {
    try {
      const updated = await api.updateUser(user.id, patch);
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không cập nhật được người dùng.");
    }
  }

  return (
    <div className="viewer-overlay" role="dialog" aria-modal="true" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="admin-shell">
        <header className="viewer-header admin-header">
          <div>
            <p className="eyebrow">Quản trị hệ thống</p>
            <h2>Kiểm soát thư viện và truy cập</h2>
          </div>
          <button className="icon-button close" onClick={onClose} title="Đóng">
            <X size={19} />
          </button>
        </header>

        <div className="admin-tabs">
          <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>
            <Activity size={16} /> Tổng quan
          </button>
          <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
            <Users size={16} /> Người dùng
          </button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>
            <ScrollText size={16} /> Nhật ký
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            <Settings size={16} /> Cấu hình API
          </button>
        </div>

        <div className="admin-body">
          {loading ? (
            <div className="viewer-state">
              <Loader2 className="spin" size={24} /> Đang tải dữ liệu quản trị...
            </div>
          ) : error ? (
            <div className="library-alert">{error}</div>
          ) : null}

          {tab === "overview" && stats ? (
            <div className="stats-grid">
              <div className="stat-card">
                <FileText size={20} />
                <span>Tổng văn bản</span>
                <strong>{stats.documents}</strong>
                <small>{stats.ready} sẵn sàng · {stats.failed} lỗi</small>
              </div>
              <div className="stat-card">
                <Database size={20} />
                <span>Trang đã xử lý</span>
                <strong>{stats.pages}</strong>
                <small>{stats.chunks} đoạn được chỉ mục</small>
              </div>
              <div className="stat-card">
                <ShieldCheck size={20} />
                <span>Người dùng</span>
                <strong>{stats.users}</strong>
                <small>{stats.processing} văn bản đang xử lý</small>
              </div>
            </div>
          ) : null}

          {tab === "users" ? (
            <div className="admin-table">
              <div className="admin-table-head">
                <span>Email</span>
                <span>Vai trò</span>
                <span>Trạng thái</span>
                <span>Ngày tạo</span>
              </div>
              {users.map((user) => (
                <div className="admin-table-row" key={user.id}>
                  <span className="user-email">{user.email}</span>
                  <select
                    value={user.role}
                    onChange={(event) => updateUser(user, { role: event.target.value as "user" | "admin" })}
                  >
                    <option value="user">Người dùng</option>
                    <option value="admin">Quản trị</option>
                  </select>
                  <button
                    className={`toggle ${user.is_active ? "on" : ""}`}
                    onClick={() => updateUser(user, { is_active: !user.is_active })}
                  >
                    {user.is_active ? "Đang hoạt động" : "Đã khóa"}
                  </button>
                  <span className="muted">{formatDate(user.created_at)}</span>
                </div>
              ))}
            </div>
          ) : null}

          {tab === "audit" ? (
            <div className="audit-list">
              {audit.length ? (
                audit.map((event) => (
                  <div className="audit-row" key={event.id}>
                    <div className="audit-icon">
                      <ScrollText size={15} />
                    </div>
                    <div>
                      <strong>{event.action}</strong>
                      <p>
                        {event.target_type || "hệ thống"} {event.target_id ? `· ${event.target_id.slice(0, 8)}` : ""}
                      </p>
                    </div>
                    <span className="muted">{formatDate(event.created_at)}</span>
                  </div>
                ))
              ) : (
                <div className="sources-empty">
                  <ScrollText size={20} />
                  <p>Chưa có sự kiện nhật ký.</p>
                </div>
              )}
            </div>
          ) : null}

          {tab === "settings" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {settingsError ? <div className="library-alert">{settingsError}</div> : null}
              {settingsSuccess ? <div className="library-alert" style={{ background: "rgba(34,197,94,0.1)", color: "#166534" }}>{settingsSuccess}</div> : null}

              <div className="stat-card" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Database size={18} />
                  <strong>LLM (OpenAI tương thích)</strong>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", width: "100%" }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span className="muted">Base URL</span>
                    <input
                      value={llmForm.base_url}
                      onChange={(e) => setLlmForm((f) => ({ ...f, base_url: e.target.value }))}
                      placeholder="http://localhost:11434/v1 hoặc https://api.example.com/v1"
                    />
                    {settings?.llm.source.base_url ? <small className="muted">Nguồn: {settings.llm.source.base_url}</small> : null}
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span className="muted">Model</span>
                    <input
                      value={llmForm.model}
                      onChange={(e) => setLlmForm((f) => ({ ...f, model: e.target.value }))}
                      placeholder="gpt-4o-mini, llama-3.1-8b, ..."
                    />
                    {settings?.llm.source.model ? <small className="muted">Nguồn: {settings.llm.source.model}</small> : null}
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span className="muted">API Key {settings?.llm.api_key_set ? "(đã thiết lập)" : "(chưa thiết lập)"}</span>
                    <input
                      type="password"
                      value={llmForm.api_key}
                      onChange={(e) => setLlmForm((f) => ({ ...f, api_key: e.target.value, api_key_clear: false }))}
                      placeholder={settings?.llm.api_key_set ? "Nhập để thay đổi..." : "Nhập API key nếu cần"}
                    />
                    {settings?.llm.api_key_set ? (
                      <button
                        type="button"
                        onClick={() => setLlmForm((f) => ({ ...f, api_key: "", api_key_clear: true }))}
                        style={{ alignSelf: "flex-start" }}
                      >
                        Xóa API key
                      </button>
                    ) : null}
                    {settings?.llm.source.api_key ? <small className="muted">Nguồn: {settings.llm.source.api_key}</small> : null}
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span className="muted">Timeout (giây)</span>
                    <input
                      type="number"
                      value={llmForm.timeout_seconds}
                      onChange={(e) => setLlmForm((f) => ({ ...f, timeout_seconds: Number(e.target.value) }))}
                    />
                  </label>
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    disabled={testingLLM}
                    onClick={async () => {
                      setSettingsError(null);
                      setSettingsSuccess(null);
                      setTestingLLM(true);
                      try {
                        const res = await api.testLLM();
                        if (res.ok) setSettingsSuccess(res.message || "Kết nối LLM thành công");
                        else setSettingsError(res.error || "Kết nối LLM thất bại");
                      } catch (err) {
                        setSettingsError(err instanceof Error ? err.message : "Kết nối LLM thất bại");
                      } finally {
                        setTestingLLM(false);
                      }
                    }}
                  >
                    {testingLLM ? <Loader2 className="spin" size={16} /> : null} Kiểm tra kết nối
                  </button>
                </div>
              </div>

              <div className="stat-card" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <FileText size={18} />
                  <strong>Embeddings (OpenAI tương thích hoặc hash)</strong>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", width: "100%" }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span className="muted">Provider</span>
                    <select
                      value={embForm.provider}
                      onChange={(e) => setEmbForm((f) => ({ ...f, provider: e.target.value as "hash" | "openai" }))}
                    >
                      <option value="hash">hash (cục bộ, không cần API)</option>
                      <option value="openai">openai (tương thích OpenAI)</option>
                    </select>
                    {settings?.embeddings.source.provider ? <small className="muted">Nguồn: {settings.embeddings.source.provider}</small> : null}
                  </label>
                  {embForm.provider === "openai" ? (
                    <>
                      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <span className="muted">Base URL</span>
                        <input
                          value={embForm.base_url}
                          onChange={(e) => setEmbForm((f) => ({ ...f, base_url: e.target.value }))}
                          placeholder="http://localhost:11434/v1 hoặc endpoint embeddings"
                        />
                        {settings?.embeddings.source.base_url ? <small className="muted">Nguồn: {settings.embeddings.source.base_url}</small> : null}
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <span className="muted">Model</span>
                        <input
                          value={embForm.model}
                          onChange={(e) => setEmbForm((f) => ({ ...f, model: e.target.value }))}
                          placeholder="text-embedding-3-small"
                        />
                        {settings?.embeddings.source.model ? <small className="muted">Nguồn: {settings.embeddings.source.model}</small> : null}
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <span className="muted">API Key {settings?.embeddings.api_key_set ? "(đã thiết lập)" : "(chưa thiết lập)"}</span>
                        <input
                          type="password"
                          value={embForm.api_key}
                          onChange={(e) => setEmbForm((f) => ({ ...f, api_key: e.target.value, api_key_clear: false }))}
                          placeholder={settings?.embeddings.api_key_set ? "Nhập để thay đổi..." : "Nhập API key nếu cần"}
                        />
                        {settings?.embeddings.api_key_set ? (
                          <button
                            type="button"
                            onClick={() => setEmbForm((f) => ({ ...f, api_key: "", api_key_clear: true }))}
                            style={{ alignSelf: "flex-start" }}
                          >
                            Xóa API key
                          </button>
                        ) : null}
                        {settings?.embeddings.source.api_key ? <small className="muted">Nguồn: {settings.embeddings.source.api_key}</small> : null}
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <span className="muted">Dimension</span>
                        <input
                          type="number"
                          value={embForm.dim}
                          onChange={(e) => setEmbForm((f) => ({ ...f, dim: Number(e.target.value) }))}
                        />
                      </label>
                    </>
                  ) : null}
                </div>
                {embForm.provider === "openai" ? (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      disabled={testingEmb}
                      onClick={async () => {
                        setSettingsError(null);
                        setSettingsSuccess(null);
                        setTestingEmb(true);
                        try {
                          const res = await api.testEmbeddings();
                          if (res.ok) setSettingsSuccess(res.message || "Kết nối Embeddings thành công");
                          else setSettingsError(res.error || "Kết nối Embeddings thất bại");
                        } catch (err) {
                          setSettingsError(err instanceof Error ? err.message : "Kết nối Embeddings thất bại");
                        } finally {
                          setTestingEmb(false);
                        }
                      }}
                    >
                      {testingEmb ? <Loader2 className="spin" size={16} /> : null} Kiểm tra kết nối
                    </button>
                  </div>
                ) : null}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  disabled={saving}
                  onClick={async () => {
                    setSettingsError(null);
                    setSettingsSuccess(null);
                    setSaving(true);
                    try {
                      const updated = await api.updateAdminSettings({
                        llm: {
                          base_url: llmForm.base_url,
                          api_key: llmForm.api_key === "" && !llmForm.api_key_clear ? undefined : llmForm.api_key,
                          api_key_clear: llmForm.api_key_clear,
                          model: llmForm.model,
                          timeout_seconds: llmForm.timeout_seconds,
                          enabled: llmForm.enabled,
                        },
                        embeddings: {
                          provider: embForm.provider,
                          base_url: embForm.base_url,
                          api_key: embForm.api_key === "" && !embForm.api_key_clear ? undefined : embForm.api_key,
                          api_key_clear: embForm.api_key_clear,
                          model: embForm.model,
                          dim: embForm.dim,
                        },
                      });
                      setSettings(updated);
                      setLlmForm((f) => ({ ...f, api_key: "", api_key_clear: false }));
                      setEmbForm((f) => ({ ...f, api_key: "", api_key_clear: false }));
                      setSettingsSuccess("Đã lưu cấu hình API");
                    } catch (err) {
                      setSettingsError(err instanceof Error ? err.message : "Không lưu được cấu hình");
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  {saving ? <Loader2 className="spin" size={16} /> : null} Lưu cấu hình
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
