import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export function renderWithProviders(ui: React.ReactElement, { route = "/" } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export interface RecordedCall {
  url: string;
  method: string;
  body?: unknown;
}

type RouteValue = unknown | ((init?: RequestInit) => unknown);

/** Stub global fetch with a `"METHOD /path"` → response-body routing table.
 *  Paths are matched with the /api/v1 prefix and query string stripped. */
export function mockFetch(routes: Record<string, RouteValue>): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = url.replace(/^\/api\/v1/, "").split("?")[0];
      calls.push({
        url: path,
        method,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      });
      const handler = routes[`${method} ${path}`];
      if (handler === undefined) {
        return jsonResponse(
          { error: { code: "NOT_FOUND", message: `no test route for ${method} ${path}` } },
          404,
        );
      }
      const data = typeof handler === "function" ? (handler as CallableFunction)(init) : handler;
      return jsonResponse(data, 200);
    }),
  );
  return calls;
}

function jsonResponse(data: unknown, status: number) {
  return {
    ok: status < 400,
    status,
    statusText: String(status),
    json: async () => data,
    blob: async () => new Blob([JSON.stringify(data)]),
  };
}

export function page<T>(items: T[]) {
  return { items, total: items.length, limit: 100, offset: 0 };
}

let idCounter = 0;
const id = (prefix: string) => `${prefix}-${++idCounter}`;

export function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: id("proj"),
    name: "Expense Tracker",
    prompt: "Build an expense tracker",
    status: "in_progress",
    token_budget: 2_000_000,
    tokens_used: 120_000,
    cost_usd: 1.23,
    human_in_loop: false,
    workflow: {
      id: id("wf"),
      status: "in_progress",
      current_stage: "engineering",
      started_at: "2026-07-07T10:00:00Z",
      finished_at: null,
      paused_reason: null,
      deadline_at: null,
    },
    created_at: "2026-07-07T10:00:00Z",
    updated_at: "2026-07-07T10:05:00Z",
    ...overrides,
  };
}

export function makeTask(overrides: Record<string, unknown> = {}) {
  return {
    id: id("task"),
    project_id: "proj-1",
    node_key: "backend_impl",
    title: "Implement the backend",
    description: "Build the API",
    status: "running",
    agent_key: "backend_engineer",
    agent_name: "Bo Backend",
    attempt: 0,
    revision_round: 0,
    output: null,
    error: null,
    depends_on: [],
    queued_at: null,
    started_at: "2026-07-07T10:01:00Z",
    finished_at: null,
    created_at: "2026-07-07T10:00:00Z",
    ...overrides,
  };
}

export function makeMessage(overrides: Record<string, unknown> = {}) {
  return {
    id: id("msg"),
    project_id: "proj-1",
    task_id: null,
    sender_agent_key: "ceo",
    sender_name: "Cleo CEO",
    recipient_agent_key: null,
    recipient_name: null,
    seq: ++idCounter,
    message_type: "result",
    content: "The vision is set.",
    payload: {},
    created_at: "2026-07-07T10:02:00Z",
    ...overrides,
  };
}
