export type PaperStatus = "unread" | "reading" | "read" | "key" | "archived";

export interface Paper {
  id: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  abstract?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
  bibkey?: string | null;
  status: PaperStatus;
  rating?: number | null;
  ai_summary?: string | null;
  note_path?: string | null;
  created_at: string;
  updated_at: string;
  has_pdf: boolean;
  pdf_url?: string | null;
  tags: string[];
  annotation_count: number;
  note_excerpt?: string;
}

export interface Annotation {
  id: number;
  page?: number | null;
  quote?: string | null;
  comment?: string | null;
  color: string;
  created_at: string;
}

export interface RelatedEntity {
  id: string;
  type: string;
  title: string;
  status?: string;
  relation: string;
  direction: "in" | "out";
}

export interface SummaryEvidence {
  role: string;
  page?: number | null;
  chunk_id: string;
  quote: string;
}

export interface SummaryRecord {
  id: number;
  mode: string;
  model?: string | null;
  summary: string;
  evidence: SummaryEvidence[];
  prompt_version: string;
  created_at: string;
}

export interface PaperDetail extends Paper {
  note: { body: string; meta: Record<string, unknown> };
  chunks_count: number;
  annotations: Annotation[];
  latest_summary?: SummaryRecord | null;
  related: RelatedEntity[];
}

export interface Idea {
  id: string;
  title: string;
  status: string;
  priority: number;
  summary?: string | null;
  path?: string | null;
  created_at: string;
  updated_at: string;
  excerpt: string;
  tags: string[];
  link_count: number;
  body?: string;
  meta?: Record<string, unknown>;
  related?: RelatedEntity[];
}

export interface Artifact {
  id: number;
  kind: string;
  path: string;
  name: string;
}

export interface MetricPoint {
  step: number;
  value: number;
}

export interface Run {
  id: string;
  experiment_id: string;
  status: string;
  params: Record<string, unknown>;
  summary: Record<string, unknown>;
  command?: string | null;
  git_commit?: string | null;
  git_dirty: boolean;
  seed?: number | null;
  host?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  artifacts: Artifact[];
  metric_keys: string[];
  metrics?: Record<string, MetricPoint[]>;
  experiment_title?: string;
}

export interface Experiment {
  id: string;
  idea_id?: string | null;
  title: string;
  hypothesis?: string | null;
  status: string;
  verdict?: string | null;
  path?: string | null;
  created_at: string;
  updated_at: string;
  run_count: number;
  latest_run?: Run | null;
  runs: Run[];
  excerpt: string;
  body?: string;
  meta?: Record<string, unknown>;
  related?: RelatedEntity[];
}

export interface Draft {
  id: string;
  title: string;
  venue?: string | null;
  status: string;
  path?: string | null;
  created_at: string;
  updated_at: string;
  word_count: number;
  excerpt: string;
  citation_count: number;
  related: RelatedEntity[];
  body?: string;
  meta?: Record<string, unknown>;
}

export interface FeedItem {
  id: number;
  arxiv_id: string;
  title: string;
  authors: string[];
  abstract?: string | null;
  published?: string | null;
  score: number;
  status: string;
  fetched_at: string;
  arxiv_url: string;
}

export interface InboxItem {
  id: number;
  content: string;
  processed?: boolean;
  created_at: string;
}

export interface Dashboard {
  greeting: string;
  today: string;
  weekday: string;
  focus: { field: string; subfield: string; questions: string[] };
  counts: Record<string, number>;
  recent_papers: Paper[];
  recent_ideas: Idea[];
  drafts: Draft[];
  feed: FeedItem[];
  inbox: InboxItem[];
  runs: Run[];
  active_experiments: {
    id: string;
    title: string;
    status: string;
    idea_id?: string | null;
    run_count: number;
  }[];
  activity: { date: string; count: number }[];
  idea_counts: Record<string, number>;
  tags: { name: string; count: number }[];
  tools: ToolsStatus;
  generated_at: string;
}

export interface ToolsStatus {
  pandoc?: string | null;
  tectonic?: string | null;
  pdf_export: boolean;
}

export interface SearchItem {
  entity_id: string;
  type: string;
  match_type: string;
  title: string;
  subtitle: string;
  snippet: string;
  page?: number | null;
  href: string;
  score: number;
  relevance: number;
}

export interface SearchResponse {
  query: string;
  items: SearchItem[];
  groups: { type: string; items: SearchItem[] }[];
  total: number;
  mode: string;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  status: string;
  degree: number;
  year?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: { source: string; target: string; relation: string }[];
  counts: Record<string, number>;
}

export interface AppSettings {
  research_field: string;
  research_focus: string;
  research_questions: string[];
  arxiv_keywords: string[];
  arxiv_categories: string[];
  bm25_title_weight: number;
  bm25_body_weight: number;
  anthropic_model: string;
  daily_feed_enabled: boolean;
  daily_feed_hour: number;
  theme: string;
  data_dir: string;
  db_path: string;
  version: string;
  has_anthropic_key: boolean;
  last_reindex?: string;
}

export interface Health {
  status: string;
  database: string;
  fts5: string;
  data_dir: string;
  data_dir_exists: boolean;
  db_size_bytes: number;
  fts_rows: number;
  tools: ToolsStatus;
  version: string;
}

export interface CompareData {
  experiment: { id: string; title: string };
  runs: {
    id: string;
    status: string;
    params: Record<string, unknown>;
    started_at?: string | null;
    finished_at?: string | null;
  }[];
  metric_keys: string[];
  series: Record<string, Record<string, MetricPoint[]>>;
  param_diff: Record<string, Record<string, unknown>>;
}

export interface ImportJob {
  id: string;
  status: string;
  progress: number;
  message: string;
  paper_id?: string | null;
  created_at: string;
  updated_at: string;
  kind: string;
}

export interface AskResponse {
  answer: string;
  citations: { page?: number | null; chunk_id: string; text: string }[];
  mode: string;
  model?: string | null;
}
