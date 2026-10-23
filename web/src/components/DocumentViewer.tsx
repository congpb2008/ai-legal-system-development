import { useEffect, useMemo, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ChevronLeft, ChevronRight, FileText, Loader2, X } from "lucide-react";
import { api } from "../api";
import type { DocumentRecord } from "../types";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

type Props = {
  document: DocumentRecord;
  pageNumber: number | null;
  bbox: number[] | null;
  onClose: () => void;
};

export function DocumentViewer({ document, pageNumber, bbox, onClose }: Props) {
  const isPdf = (document.original_filename || "").toLowerCase().endsWith(".pdf");
  const [pdf, setPdf] = useState<any>(null);
  const [numPages, setNumPages] = useState(document.page_count || 1);
  const [page, setPage] = useState(pageNumber || 1);
  const [loading, setLoading] = useState(isPdf);
  const [error, setError] = useState<string | null>(null);
  const [pageText, setPageText] = useState("");
  const [textLoading, setTextLoading] = useState(!isPdf);
  const [containerWidth, setContainerWidth] = useState(0);
  const [viewScale, setViewScale] = useState(1);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const renderTaskRef = useRef<{ cancel: () => void; promise: Promise<void> } | null>(null);

  useEffect(() => {
    setPage(pageNumber || 1);
  }, [pageNumber, document.id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (!isPdf) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(api.documentFileUrl(document.id), { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error("Không tải được tệp PDF.");
        return response.arrayBuffer();
      })
      .then(async (buffer) => {
        if (cancelled) return;
        const loaded = await pdfjsLib.getDocument({ data: new Uint8Array(buffer) }).promise;
        if (cancelled) return;
        setPdf(loaded);
        setNumPages(loaded.numPages);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Không tải được PDF.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [document.id, isPdf]);

  useEffect(() => {
    if (isPdf) return;
    let cancelled = false;
    setTextLoading(true);
    api
      .pageText(document.id, page)
      .then((payload) => {
        if (!cancelled) setPageText(payload.text);
      })
      .catch(() => {
        if (!cancelled) setPageText("");
      })
      .finally(() => {
        if (!cancelled) setTextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [document.id, isPdf, page]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width) setContainerWidth(width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvasRef.current) return;
    let cancelled = false;
    const render = async () => {
      const pdfPage = await pdf.getPage(Math.min(page, numPages));
      if (cancelled) return;
      const base = pdfPage.getViewport({ scale: 1 });
      const available = Math.max(320, (containerWidth || containerRef.current?.clientWidth || 720) - 32);
      const scale = Math.min(1.55, available / base.width);
      const cssViewport = pdfPage.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const renderViewport = pdfPage.getViewport({ scale: scale * ratio });
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = Math.floor(renderViewport.width);
      canvas.height = Math.floor(renderViewport.height);
      canvas.style.width = `${Math.floor(cssViewport.width)}px`;
      canvas.style.height = `${Math.floor(cssViewport.height)}px`;
      const context = canvas.getContext("2d");
      if (!context) return;
      renderTaskRef.current?.cancel();
      const task = pdfPage.render({ canvasContext: context, viewport: renderViewport });
      renderTaskRef.current = task;
      await task.promise;
      if (cancelled) return;
      setViewScale(scale);
      setPageSize({ width: cssViewport.width, height: cssViewport.height });
    };
    render().catch((err) => {
      if (!cancelled && !(err instanceof Error && err.name === "RenderingCancelledException")) {
        setError("Không hiển thị được trang PDF.");
      }
    });
    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
    };
  }, [pdf, page, numPages, containerWidth]);

  const highlight = useMemo(() => {
    if (!bbox || bbox.length !== 4 || !pageSize.width) return null;
    return {
      left: bbox[0] * viewScale,
      top: bbox[1] * viewScale,
      width: Math.max(6, (bbox[2] - bbox[0]) * viewScale),
      height: Math.max(6, (bbox[3] - bbox[1]) * viewScale),
    };
  }, [bbox, pageSize.width, viewScale]);

  const changePage = (next: number) => {
    setPage(Math.min(Math.max(1, next), numPages));
  };

  return (
    <div className="viewer-overlay" role="dialog" aria-modal="true" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="viewer-shell">
        <header className="viewer-header">
          <div>
            <p className="eyebrow">Bản gốc</p>
            <h2>{document.title}</h2>
            <span>{document.document_number || document.original_filename}</span>
          </div>
          <div className="viewer-nav">
            <button className="icon-button" onClick={() => changePage(page - 1)} disabled={page <= 1} title="Trang trước">
              <ChevronLeft size={18} />
            </button>
            <span>
              Trang {page} / {numPages}
            </span>
            <button className="icon-button" onClick={() => changePage(page + 1)} disabled={page >= numPages} title="Trang sau">
              <ChevronRight size={18} />
            </button>
            <button className="icon-button close" onClick={onClose} title="Đóng">
              <X size={19} />
            </button>
          </div>
        </header>

        <div className="viewer-body" ref={containerRef}>
          {loading ? (
            <div className="viewer-state">
              <Loader2 className="spin" size={24} />
              <span>Đang tải bản gốc...</span>
            </div>
          ) : error ? (
            <div className="viewer-state error">{error}</div>
          ) : isPdf ? (
            <div className="pdf-page-wrap" style={{ width: pageSize.width || undefined, height: pageSize.height || undefined }}>
              <canvas ref={canvasRef} />
              {highlight ? <div className="pdf-highlight" style={highlight} /> : null}
            </div>
          ) : textLoading ? (
            <div className="viewer-state">
              <Loader2 className="spin" size={24} />
            </div>
          ) : (
            <div className="docx-text">
              <div className="docx-text-head">
                <FileText size={16} /> Trang {page}
              </div>
              <pre>{pageText || "Không có nội dung văn bản cho trang này."}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
