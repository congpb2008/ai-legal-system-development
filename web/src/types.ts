export type User = {
  id: string;
  email: string;
  role: "admin" | "user";
};

export type DocumentRecord = {
  id: string;
  title: string;
  document_number: string | null;
  document_type: string | null;
  issuer: string | null;
  issued_date: string | null;
  effective_date: string | null;
  status: "processing" | "ready" | "failed" | string;
  page_count: number;
  created_at: string;
  owner_id: string | null;
  original_filename: string | null;
};

export type LegalNode = {
  id: string;
  parent_id: string | null;
  level: string;
  number: string | null;
  title: string;
  text: string;
  path: string;
  order_index: number;
  page_start: number | null;
  page_end: number | null;
  bbox: number[] | null;
  confidence: number;
  extraction_method: string;
};

export type SearchResult = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_number: string | null;
  legal_path: string;
  node_level: string;
  text: string;
  snippet: string;
  page_number: number | null;
  bbox: number[] | null;
  score: number;
};

export type Citation = {
  index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_number: string | null;
  legal_path: string;
  page_number: number | null;
  bbox: number[] | null;
  quote: string;
};

export type Job = {
  id: string;
  document_file_id: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AdminStats = {
  documents: number;
  ready: number;
  processing: number;
  failed: number;
  pages: number;
  chunks: number;
  users: number;
};

export type AdminUser = {
  id: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type PageLine = {
  text: string;
  bbox: number[];
};

export type PageRecord = {
  id: string;
  page_number: number;
  width: number | null;
  height: number | null;
  image_path: string | null;
  text: string;
  lines: PageLine[];
  text_source: string;
  ocr_confidence: number | null;
};

export type DocumentTreeNode = LegalNode & {
  children: DocumentTreeNode[];
};

export type LLMSettings = {
  base_url: string;
  api_key_set: boolean;
  model: string;
  timeout_seconds: number;
  enabled: boolean;
  source: Record<string, string>;
};

export type EmbeddingSettings = {
  provider: "hash" | "openai";
  base_url: string;
  api_key_set: boolean;
  model: string;
  dim: number;
  source: Record<string, string>;
};

export type AdminSettings = {
  llm: LLMSettings;
  embeddings: EmbeddingSettings;
};
