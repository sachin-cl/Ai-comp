export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "member";
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface WorkflowInfo {
  id: string | null;
  status: string;
  current_stage: string;
  started_at: string | null;
  finished_at: string | null;
  paused_reason: string | null;
  deadline_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  prompt: string;
  status: string;
  token_budget: number;
  tokens_used: number;
  cost_usd: number;
  human_in_loop: boolean;
  workflow: WorkflowInfo | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  project_id: string;
  node_key: string;
  title: string;
  description: string;
  status: string;
  agent_key: string;
  agent_name: string;
  attempt: number;
  revision_round: number;
  output: Record<string, unknown> | null;
  error: string | null;
  depends_on: string[];
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  reviews?: Review[];
}

export interface Review {
  verdict: string;
  reasons: ReviewReason[];
  round: number;
  created_at: string;
}

export interface ReviewReason {
  severity: string;
  area: string;
  target_node: string;
  description: string;
  suggestion: string;
}

export interface Message {
  id: string;
  project_id: string;
  task_id: string | null;
  sender_agent_key: string | null;
  sender_name: string | null;
  recipient_agent_key: string | null;
  recipient_name: string | null;
  seq: number;
  message_type: string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Artifact {
  id: string;
  path: string;
  language: string;
  latest_version: number;
  size_bytes: number | null;
  validation_ok: boolean | null;
  updated_at: string | null;
}

export interface ArtifactContent {
  id: string;
  path: string;
  language: string;
  version: number;
  content: string;
  content_hash: string;
  size_bytes: number;
  validation: { tool?: string; ok?: boolean; issues?: string[] };
  created_at: string | null;
}

export interface ArtifactVersionInfo {
  version: number;
  content_hash: string;
  size_bytes: number;
  validation_ok: boolean | null;
  created_at: string | null;
}

export interface Agent {
  key: string;
  name: string;
  role_title: string;
  personality: string;
  provider: string;
  model: string;
  is_active: boolean;
}

export interface AgentStats {
  agent_key: string;
  name?: string;
  role_title?: string;
  tasks_completed: number;
  tasks_total: number;
  revision_rate: number;
  avg_tokens: number;
  avg_latency_ms: number;
  cost_usd: number;
  llm_calls: number;
}

export interface Notification {
  id: string;
  project_id: string | null;
  type: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimelineSpan {
  task_id: string;
  node_key: string;
  title: string;
  status: string;
  revision_round: number;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Timeline {
  project_id: string;
  workflow: {
    status: string;
    current_stage: string;
    started_at: string | null;
    finished_at: string | null;
    deadline_at: string | null;
  };
  spans: TimelineSpan[];
}

export interface AnalyticsOverview {
  projects_by_status: Record<string, number>;
  total_tokens: number;
  total_cost_usd: number;
  agents: AgentStats[];
}

export interface WsEvent {
  type: string;
  project_id?: string;
  ts?: string;
  [key: string]: unknown;
}
