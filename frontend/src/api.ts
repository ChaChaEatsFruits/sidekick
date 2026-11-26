// Client for the Sidekick HTTP API. Paths are relative; in dev the Vite proxy forwards /api
// to FastAPI, and in a build FastAPI serves this app itself, so the browser sees one origin.
import type { Message } from "./lib/messages";

export type Status = "starting" | "ready" | "running" | "paused" | "error";

export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export interface Snapshot {
  status: Status;
  plan: Todo[];
  messages: Message[];
  error: string | null;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI sends a string detail for our own errors and a list for validation errors
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
  }
  return body as T;
}

const post = <T>(path: string, json?: unknown) =>
  call<T>(path, {
    method: "POST",
    headers: json === undefined ? undefined : { "Content-Type": "application/json" },
    body: json === undefined ? undefined : JSON.stringify(json),
  });

export const startTask = (message: string, success_criteria: string) =>
  post<Snapshot>("/api/tasks", { message, success_criteria });
export const approve = (approve: boolean) => post<Snapshot>("/api/approve", { approve });
export const reset = () => post<Snapshot>("/api/session");

export const listKb = () => call<{ files: string[] }>("/api/kb");
export const reindexKb = () => post<{ chunks: number; files: string[] }>("/api/kb/reindex");
export function uploadKb(files: FileList) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return call<{ files: string[] }>("/api/kb", { method: "POST", body: form });
}
