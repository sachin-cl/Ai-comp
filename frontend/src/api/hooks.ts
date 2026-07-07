import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, patch, post } from "./client";
import type {
  Agent,
  AgentStats,
  AnalyticsOverview,
  Artifact,
  ArtifactContent,
  ArtifactVersionInfo,
  Message,
  Notification,
  Page,
  Project,
  Task,
  Timeline,
  TokenResponse,
  User,
} from "../types";

// ---------- auth ----------
export const useMe = (enabled: boolean) =>
  useQuery({ queryKey: ["me"], queryFn: () => get<User>("/auth/me"), enabled, retry: false });

export const useLogin = () =>
  useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      post<TokenResponse>("/auth/login", body),
  });

export const useRegister = () =>
  useMutation({
    mutationFn: (body: { email: string; password: string; full_name: string }) =>
      post<User>("/auth/register", body),
  });

// ---------- projects ----------
export const useProjects = () =>
  useQuery({
    queryKey: ["projects"],
    queryFn: () => get<Page<Project>>("/projects?limit=100"),
    refetchInterval: 15_000,
  });

export const useProject = (id: string) =>
  useQuery({
    queryKey: ["projects", id],
    queryFn: () => get<Project>(`/projects/${id}`),
    refetchInterval: 10_000,
  });

export const useCreateProject = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name: string;
      prompt: string;
      human_in_loop?: boolean;
      token_budget?: number;
    }) => post<Project>("/projects", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
};

export const useProjectAction = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, body }: { action: "cancel" | "resume" | "approve"; body?: unknown }) =>
      post<Project>(`/projects/${id}/${action}`, body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
};

export const useTimeline = (id: string) =>
  useQuery({
    queryKey: ["projects", id, "timeline"],
    queryFn: () => get<Timeline>(`/projects/${id}/timeline`),
    refetchInterval: 10_000,
  });

// ---------- tasks ----------
export const useProjectTasks = (id: string) =>
  useQuery({
    queryKey: ["projects", id, "tasks"],
    queryFn: () => get<Task[]>(`/projects/${id}/tasks`),
    refetchInterval: 8_000,
  });

export const useTask = (taskId: string | null) =>
  useQuery({
    queryKey: ["tasks", taskId],
    queryFn: () => get<Task>(`/tasks/${taskId}`),
    enabled: !!taskId,
  });

export const useRetryTask = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => post<Task>(`/tasks/${taskId}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects", projectId, "tasks"] }),
  });
};

// ---------- messages ----------
export const useProjectMessages = (id: string) =>
  useQuery({
    queryKey: ["projects", id, "messages"],
    queryFn: () => get<Page<Message>>(`/projects/${id}/messages?limit=500`),
    refetchInterval: 6_000,
  });

// ---------- artifacts ----------
export const useProjectArtifacts = (id: string) =>
  useQuery({
    queryKey: ["projects", id, "artifacts"],
    queryFn: () => get<Artifact[]>(`/projects/${id}/artifacts`),
    refetchInterval: 10_000,
  });

export const useArtifact = (artifactId: string | null) =>
  useQuery({
    queryKey: ["artifacts", artifactId],
    queryFn: () => get<ArtifactContent>(`/artifacts/${artifactId}`),
    enabled: !!artifactId,
  });

export const useArtifactVersions = (artifactId: string | null) =>
  useQuery({
    queryKey: ["artifacts", artifactId, "versions"],
    queryFn: () => get<ArtifactVersionInfo[]>(`/artifacts/${artifactId}/versions`),
    enabled: !!artifactId,
  });

// ---------- agents / analytics ----------
export const useAgents = () =>
  useQuery({ queryKey: ["agents"], queryFn: () => get<Agent[]>("/agents") });

export const useAgentStats = (key: string | null) =>
  useQuery({
    queryKey: ["agents", key, "stats"],
    queryFn: () => get<AgentStats>(`/agents/${key}/stats`),
    enabled: !!key,
  });

export const useAnalytics = () =>
  useQuery({
    queryKey: ["analytics"],
    queryFn: () => get<AnalyticsOverview>("/analytics/overview"),
    refetchInterval: 20_000,
  });

// ---------- notifications ----------
export const useNotifications = () =>
  useQuery({
    queryKey: ["notifications"],
    queryFn: () => get<Page<Notification>>("/notifications?limit=50"),
    refetchInterval: 20_000,
  });

export const useMarkRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string | "all") =>
      id === "all" ? post<void>("/notifications/read-all") : post<void>(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};

export const useUpdateProject = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => patch<Project>(`/projects/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects", id] }),
  });
};
