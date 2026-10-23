import { BookOpenCheck, ChevronRight, Clock3, FileText, MapPin } from "lucide-react";
import type { Citation, SearchResult } from "../types";

type Props = {
  sources: SearchResult[];
  citations: Citation[];
  timings: Record<string, number>;
  activeChunkId: string | null;
  onOpen: (source: SearchResult) => void;
};

export function SourcesPanel({ sources, citations, timings, activeChunkId, onOpen }: Props) {
  const citationByChunk = new Map(citations.map((citation) => [citation.chunk_id, citation]));
  const maxScore = sources.reduce((highest, source) => Math.max(highest, source.score), 0);

  return (
    <aside className="sources-pane">
      <header className="pane-header sources-header">
        <div>
          <p className="eyebrow">Nguồn trích dẫn</p>
          <h2>{sources.length ? `${sources.length} kết quả liên quan` : "Chưa có nguồn"}</h2>
        </div>
        {timings.retrieval_ms ? (
          <span className="timing-badge">
            <Clock3 size={13} /> {timings.retrieval_ms} ms
          </span>
        ) : null}
      </header>

      <div className="sources-body">
        {!sources.length ? (
          <div className="sources-empty">
            <div className="empty-mark small">
              <BookOpenCheck size={19} />
            </div>
            <h3>Nguồn sẽ xuất hiện ở đây</h3>
            <p>Khi bạn gửi câu hỏi, các điều khoản liên quan sẽ được hiển thị trước câu trả lời.</p>
          </div>
        ) : (
          <div className="source-list">
            {sources.map((source, index) => {
              const citation = citationByChunk.get(source.chunk_id);
              const citationIndex = citation?.index ?? index + 1;
              const relevance = maxScore > 0 ? Math.round((source.score / maxScore) * 100) : 0;
              return (
                <button
                  key={source.chunk_id}
                  className={`source-card ${activeChunkId === source.chunk_id ? "active" : ""}`}
                  onClick={() => onOpen(source)}
                >
                  <div className="source-card-top">
                    <span className="citation-index">[{citationIndex}]</span>
                    <span className="source-score" title="Độ liên quan tương đối">
                      {relevance}%
                    </span>
                  </div>
                  <h4>{source.document_title}</h4>
                  {source.document_number ? <p className="source-number">{source.document_number}</p> : null}
                  <div className="source-location">
                    <MapPin size={13} />
                    <span>{source.legal_path || "Chưa xác định cấu trúc"}</span>
                  </div>
                  <p className="source-snippet">{source.snippet}</p>
                  <div className="source-footer">
                    <span>
                      <FileText size={13} /> Trang {source.page_number ?? "—"}
                    </span>
                    <span className="source-open">
                      Xem bản gốc <ChevronRight size={14} />
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
