import { useMemo, useRef } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  useMessagePartText,
  type ChatModelAdapter,
  type ChatModelRunResult,
  type ThreadMessage,
} from "@assistant-ui/react";
import ReactMarkdown from "react-markdown";
import { ArrowUp, Bot, CircleSlash2, Sparkles, UserRound, X } from "lucide-react";
import type { Citation, SearchResult } from "../types";

type Props = {
  selectedDocumentId: string | null;
  selectedDocumentTitle: string | null;
  onClearFilter: () => void;
  onSources: (sources: SearchResult[]) => void;
  onCitations: (citations: Citation[]) => void;
  onTimings: (timings: Record<string, number>) => void;
};

type SseEvent = {
  event: string;
  data: Record<string, unknown>;
};

async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  if (!response.body) throw new Error("Máy chủ không trả về luồng dữ liệu.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      try {
        yield { event, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
      } catch {
        // Ignore malformed keep-alive chunks.
      }
    }
  }
}

function messageText(message: ThreadMessage): string {
  return message.content
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

function MessageText() {
  const part = useMessagePartText() as any;
  if (!part || typeof part.text !== "string") return null;
  return <ReactMarkdown>{part.text}</ReactMarkdown>;
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="message-row user-row">
      <div className="message-avatar user-avatar">
        <UserRound size={15} />
      </div>
      <div className="message-bubble user-bubble">
        <MessagePrimitive.Parts components={{ Text: MessageText }} />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="message-row assistant-row">
      <div className="message-avatar assistant-avatar">
        <Bot size={16} />
      </div>
      <div className="assistant-message-body">
        <div className="message-label">
          <span>Trợ lý pháp chế</span>
          <span className="message-label-dot" />
        </div>
        <div className="message-bubble assistant-bubble">
          <MessagePrimitive.Parts components={{ Text: MessageText }} />
          <MessagePrimitive.Error>
            <div className="message-error">
              <CircleSlash2 size={15} /> Không thể nhận câu trả lời. Vui lòng thử lại.
            </div>
          </MessagePrimitive.Error>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

const messageComponents = {
  UserMessage,
  AssistantMessage,
};

export function ChatPane({
  selectedDocumentId,
  selectedDocumentTitle,
  onClearFilter,
  onSources,
  onCitations,
  onTimings,
}: Props) {
  const filterRef = useRef<string | null>(selectedDocumentId);
  const sourcesRef = useRef(onSources);
  const citationsRef = useRef(onCitations);
  const timingsRef = useRef(onTimings);
  filterRef.current = selectedDocumentId;
  sourcesRef.current = onSources;
  citationsRef.current = onCitations;
  timingsRef.current = onTimings;

  const adapter = useMemo<ChatModelAdapter>(
    () => ({
      async *run({ messages, abortSignal }): AsyncGenerator<ChatModelRunResult, void> {
        const last = messages[messages.length - 1];
        const question = last ? messageText(last) : "";
        if (!question) return;

        const history = messages
          .slice(0, -1)
          .filter((message) => message.role === "user" || message.role === "assistant")
          .slice(-8)
          .map((message) => ({ role: message.role, content: messageText(message) }))
          .filter((message) => message.content);

        sourcesRef.current([]);
        citationsRef.current([]);

        const documentIds = filterRef.current ? [filterRef.current] : undefined;
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: question,
            history,
            top_k: 8,
            generate_answer: true,
            document_ids: documentIds,
          }),
          signal: abortSignal,
        });

        if (!response.ok) {
          let detail = "Không thể gửi câu hỏi.";
          try {
            const payload = await response.json();
            if (typeof payload.detail === "string") detail = payload.detail;
          } catch {
            // keep fallback
          }
          throw new Error(detail);
        }

        let answer = "";
        for await (const event of readSse(response)) {
          if (abortSignal.aborted) return;
          if (event.event === "sources") {
            sourcesRef.current((event.data.sources as SearchResult[]) ?? []);
          } else if (event.event === "token") {
            answer += String(event.data.text ?? "");
            yield {
              content: [{ type: "text", text: answer }],
              status: { type: "running" },
            };
          } else if (event.event === "done") {
            const finalAnswer = String(event.data.answer ?? answer);
            citationsRef.current((event.data.citations as Citation[]) ?? []);
            if (event.data.timings && typeof event.data.timings === "object") {
              timingsRef.current(event.data.timings as Record<string, number>);
            }
            yield {
              content: [{ type: "text", text: finalAnswer || answer || "Tôi không tìm thấy đủ căn cứ." }],
              status: { type: "complete", reason: "stop" },
            };
          } else if (event.event === "error") {
            throw new Error(String(event.data.message ?? "Lỗi khi tạo câu trả lời."));
          }
        }
      },
    }),
    [],
  );

  const runtime = useLocalRuntime(adapter);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <section className="chat-pane">
        <header className="pane-header chat-header">
          <div>
            <p className="eyebrow">Tra cứu có căn cứ</p>
            <h2>Hỏi về văn bản pháp luật</h2>
          </div>
          <div className="chat-header-meta">
            {selectedDocumentTitle ? (
              <button className="filter-chip" onClick={onClearFilter} title="Bỏ giới hạn tài liệu">
                <span>{selectedDocumentTitle}</span>
                <X size={14} />
              </button>
            ) : (
              <span className="library-wide">
                <Sparkles size={14} /> Toàn bộ thư viện
              </span>
            )}
          </div>
        </header>

        <ThreadPrimitive.Root className="thread-root">
          <ThreadPrimitive.Viewport className="thread-viewport">
            <ThreadPrimitive.Empty>
              <div className="thread-empty">
                <div className="empty-mark">
                  <Sparkles size={22} />
                </div>
                <h3>Tìm quy định, không đoán nội dung</h3>
                <p>
                  Đặt câu hỏi về điều kiện, hồ sơ, thẩm quyền hoặc nghĩa vụ. Câu trả lời sẽ nêu rõ Điều, Khoản, Điểm và
                  trang nguồn để bạn đối chiếu.
                </p>
                <div className="prompt-grid">
                  <div>
                    <strong>Điều kiện cấp tín dụng</strong>
                    <span>Khách hàng cần đáp ứng những điều kiện nào?</span>
                  </div>
                  <div>
                    <strong>Hồ sơ đề nghị cấp tín dụng</strong>
                    <span>Thành phần hồ sơ gồm những tài liệu gì?</span>
                  </div>
                  <div>
                    <strong>Thẩm quyền phê duyệt</strong>
                    <span>Ai có thẩm quyền quyết định cấp tín dụng?</span>
                  </div>
                </div>
              </div>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={messageComponents} />
          </ThreadPrimitive.Viewport>
          <ThreadPrimitive.ViewportFooter className="composer-wrap">
            <ComposerPrimitive.Root className="composer">
              <ComposerPrimitive.Input
                className="composer-input"
                placeholder="Hỏi về điều kiện, hồ sơ, thẩm quyền... (Enter để gửi)"
                rows={2}
                autoFocus
              />
              <div className="composer-footer">
                <span>Chỉ tra cứu văn bản, không phải tư vấn pháp lý cá nhân.</span>
                <ComposerPrimitive.Send className="send-button" title="Gửi câu hỏi">
                  Gửi <ArrowUp size={16} />
                </ComposerPrimitive.Send>
              </div>
            </ComposerPrimitive.Root>
          </ThreadPrimitive.ViewportFooter>
        </ThreadPrimitive.Root>
      </section>
    </AssistantRuntimeProvider>
  );
}
