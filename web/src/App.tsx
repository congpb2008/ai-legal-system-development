import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Loader2, LogOut, Scale, Settings2, ShieldCheck } from "lucide-react";
import { api } from "./api";
import { AdminPanel } from "./components/AdminPanel";
import { AuthScreen } from "./components/AuthScreen";
import { ChatPane } from "./components/ChatPane";
import { DocumentLibrary } from "./components/DocumentLibrary";
import { SourcesPanel } from "./components/SourcesPanel";
import type { Citation, DocumentRecord, SearchResult, User } from "./types";

const DocumentViewer = lazy(() =>
  import("./components/DocumentViewer").then((module) => ({ default: module.DocumentViewer })),
);

type ViewerState = {
  document: DocumentRecord;
  page: number;
  bbox: number[] | null;
};

function LoadingScreen() {
  return (
    <div className="boot-screen">
      <div className="brand-mark">
        <Scale size={26} />
      </div>
      <p>Đang kết nối thư viện pháp chế...</p>
    </div>
  );
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [sources, setSources] = useState<SearchResult[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [timings, setTimings] = useState<Record<string, number>>({});
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);
  const [viewer, setViewer] = useState<ViewerState | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const next = await api.documents();
      setDocuments(next);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không tải được thư viện.");
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  useEffect(() => {
    if (!documents.some((document) => document.status === "processing")) return;
    const timer = window.setInterval(() => {
      void refreshDocuments();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [documents, refreshDocuments]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );

  async function upload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      const document = await api.uploadDocument(file);
      setDocuments((current) => [document, ...current.filter((item) => item.id !== document.id)]);
      setNotice(`Đã nhận "${document.title}". Hệ thống đang xử lý và lập chỉ mục.`);
      void refreshDocuments();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không tải được văn bản.");
    } finally {
      setUploading(false);
    }
  }

  async function removeDocument(document: DocumentRecord) {
    if (!window.confirm(`Xóa "${document.title}" khỏi thư viện? Thao tác này không thể hoàn tác.`)) return;
    try {
      await api.deleteDocument(document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      if (selectedDocumentId === document.id) setSelectedDocumentId(null);
      setNotice("Đã xóa văn bản và toàn bộ chỉ mục liên quan.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không xóa được văn bản.");
    }
  }

  async function reindexDocument(document: DocumentRecord) {
    try {
      await api.reindexDocument(document.id);
      setDocuments((current) =>
        current.map((item) => (item.id === document.id ? { ...item, status: "processing" } : item)),
      );
      setNotice("Đã đưa văn bản vào hàng đợi xử lý lại.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không xử lý lại được văn bản.");
    }
  }

  async function openSource(source: SearchResult) {
    setActiveChunkId(source.chunk_id);
    let document = documents.find((item) => item.id === source.document_id);
    if (!document) {
      try {
        document = await api.document(source.document_id);
        setDocuments((current) => [document as DocumentRecord, ...current]);
      } catch {
        setNotice("Không tìm thấy tài liệu nguồn.");
        return;
      }
    }
    setViewer({ document, page: source.page_number || 1, bbox: source.bbox });
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <div className="brand-mark">
            <Scale size={21} />
          </div>
          <div>
            <strong>Trợ lý Pháp chế Ngân hàng</strong>
            <span>Tra cứu văn bản nội bộ</span>
          </div>
        </div>

        <div className="header-pills">
          <span className="header-pill">
            <BookOpen size={14} /> Thư viện dùng chung
          </span>
          {user.role === "admin" ? (
            <span className="header-pill admin-pill">
              <ShieldCheck size={14} /> Quản trị
            </span>
          ) : null}
        </div>

        <div className="header-actions">
          <div className="user-chip">
            <span className="user-avatar">{user.email.slice(0, 1).toUpperCase()}</span>
            <div>
              <strong>{user.email}</strong>
              <span>{user.role === "admin" ? "Quản trị viên" : "Người dùng"}</span>
            </div>
          </div>
          {user.role === "admin" ? (
            <button className="icon-button" onClick={() => setAdminOpen(true)} title="Quản trị hệ thống">
              <Settings2 size={18} />
            </button>
          ) : null}
          <button className="icon-button" onClick={onLogout} title="Đăng xuất">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {notice ? (
        <div className="app-notice" onClick={() => setNotice(null)}>
          {notice}
        </div>
      ) : null}

      <main className="workspace-grid">
        <DocumentLibrary
          documents={documents}
          selectedId={selectedDocumentId}
          user={user}
          uploading={uploading}
          uploadError={uploadError}
          onSelect={(document) => setSelectedDocumentId(document.id)}
          onClearSelection={() => setSelectedDocumentId(null)}
          onUpload={upload}
          onDelete={removeDocument}
          onReindex={reindexDocument}
        />
        <ChatPane
          selectedDocumentId={selectedDocumentId}
          selectedDocumentTitle={selectedDocument?.title ?? null}
          onClearFilter={() => setSelectedDocumentId(null)}
          onSources={setSources}
          onCitations={setCitations}
          onTimings={setTimings}
        />
        <SourcesPanel
          sources={sources}
          citations={citations}
          timings={timings}
          activeChunkId={activeChunkId}
          onOpen={openSource}
        />
      </main>

      {viewer ? (
        <Suspense
          fallback={
            <div className="viewer-overlay">
              <div className="viewer-state">
                <Loader2 className="spin" size={24} /> Đang mở bản gốc...
              </div>
            </div>
          }
        >
          <DocumentViewer
            document={viewer.document}
            pageNumber={viewer.page}
            bbox={viewer.bbox}
            onClose={() => setViewer(null)}
          />
        </Suspense>
      ) : null}

      {adminOpen ? <AdminPanel onClose={() => setAdminOpen(false)} /> : null}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api
      .me()
      .then((current) => setUser(current))
      .catch(() => setUser(null));
  }, []);

  async function logout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }

  if (user === undefined) return <LoadingScreen />;
  if (!user) return <AuthScreen onAuthenticated={setUser} />;
  return <Workspace user={user} onLogout={logout} />;
}
