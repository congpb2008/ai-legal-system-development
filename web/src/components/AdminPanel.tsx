import { useEffect, useState } from "react";
import { Activity, Database, FileText, Loader2, ScrollText, ShieldCheck, Users, X } from "lucide-react";
import { api } from "../api";
import type { AdminStats, AdminUser, AuditEvent } from "../types";

type Props = {
  onClose: () => void;
};

type Tab = "overview" | "users" | "audit";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [nextStats, nextUsers, nextAudit] = await Promise.all([api.adminStats(), api.adminUsers(), api.adminAudit()]);
      setStats(nextStats);
      setUsers(nextUsers);
      setAudit(nextAudit);
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
        </div>
      </div>
    </div>
  );
}
