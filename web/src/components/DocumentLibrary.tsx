import { useRef } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Filter,
  Library,
  Loader2,
  RefreshCw,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import type { DocumentRecord, User } from "../types";

type Props = {
  documents: DocumentRecord[];
  selectedId: string | null;
  user: User;
  uploading: boolean;
  uploadError: string | null;
  onSelect: (document: DocumentRecord) => void;
  onClearSelection: () => void;
  onUpload: (file: File) => void;
  onDelete: (document: DocumentRecord) => void;
  onReindex: (document: DocumentRecord) => void;
};

function StatusBadge({ status }: { status: string }) {
  if (status === "ready") {
    return (
      <span className="status-badge ready">
        <CheckCircle2 size={12} /> Sẵn sàng
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="status-badge failed">
        <AlertCircle size={12} /> Lỗi xử lý
      </span>
    );
  }
  return (
    <span className="status-badge processing">
      <Loader2 size={12} className="spin" /> Đang xử lý
    </span>
  );
}

export function DocumentLibrary({
  documents,
  selectedId,
  user,
  uploading,
  uploadError,
  onSelect,
  onClearSelection,
  onUpload,
  onDelete,
  onReindex,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const readyCount = documents.filter((document) => document.status === "ready").length;

  return (
    <aside className="library-pane">
      <header className="library-header">
        <div className="library-title">
          <div className="brand-mark small">
            <Library size={17} />
          </div>
          <div>
            <p className="eyebrow">Thư viện dùng chung</p>
            <h2>Văn bản pháp luật</h2>
          </div>
        </div>
        <button className="icon-button" onClick={() => inputRef.current?.click()} title="Tải văn bản lên" disabled={uploading}>
          {uploading ? <Loader2 size={17} className="spin" /> : <UploadCloud size={17} />}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
        />
      </header>

      <div className="library-summary">
        <span>{documents.length} văn bản</span>
        <span className="dot-separator">·</span>
        <span>{readyCount} sẵn sàng</span>
      </div>

      {uploadError ? <div className="library-alert">{uploadError}</div> : null}

      {selectedId ? (
        <button className="clear-filter" onClick={onClearSelection}>
          <Filter size={13} /> Đang giới hạn một văn bản <X size={13} />
        </button>
      ) : null}

      <div className="document-list">
        {!documents.length ? (
          <div className="library-empty">
            <FileText size={22} />
            <p>Chưa có văn bản. Tải PDF hoặc DOCX đầu tiên để bắt đầu.</p>
          </div>
        ) : null}
        {documents.map((document) => (
          <div
            key={document.id}
            className={`document-card ${selectedId === document.id ? "selected" : ""}`}
            onClick={() => onSelect(document)}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(document);
              }
            }}
          >
            <div className="document-card-head">
              <span className="document-icon">
                <FileText size={16} />
              </span>
              <div className="document-card-title">
                <strong>{document.title}</strong>
                <span>{document.document_type || "Văn bản pháp luật"}</span>
              </div>
            </div>
            <div className="document-card-meta">
              <StatusBadge status={document.status} />
              <span>{document.page_count ? `${document.page_count} trang` : "—"}</span>
            </div>
            {document.document_number ? <p className="document-number">{document.document_number}</p> : null}
            <div className="document-actions">
              {user.role === "admin" ? (
                <button
                  className="mini-button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onReindex(document);
                  }}
                  title="Xử lý lại văn bản"
                >
                  <RefreshCw size={13} /> Xử lý lại
                </button>
              ) : null}
              {user.role === "admin" || document.owner_id === user.id ? (
                <button
                  className="mini-button danger"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(document);
                  }}
                  title="Xóa văn bản"
                >
                  <Trash2 size={13} /> Xóa
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      <footer className="library-footer">
        <UploadCloud size={16} />
        <span>Hỗ trợ PDF và DOCX. Văn bản scan được OCR khi xử lý.</span>
      </footer>
    </aside>
  );
}
