export type Lesson = { lesson: string; score: number };
export type Classified = { intent: string; prompt?: string; lessons?: Lesson[] };
export type AuditFilters = {
  page: number;
  page_size: number;
  actor_user_id?: string | null;
  action?: string | null;
  category?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  automated_only?: boolean | null;
};
export type AuditRecordSummary = {
  id: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  details: Record<string, unknown>;
  actor_name: string | null;
  actor_role: string | null;
  actor_email: string | null;
  created_at: string;
  automated: boolean;
};
export type AuditResult = {
  answer: string;
  filters: AuditFilters;
  records: AuditRecordSummary[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
};
export type ChatResponse =
  | {
      kind: "intent";
      text: string;
      intent: string;
      prompt: string;
      lessons: Lesson[];
    }
  | {
      kind: "audit_results";
      intent: "audit_query";
      result: AuditResult;
    };
export type HawkeyeSession = {
  user: {
    id: string;
    organization_id: string;
    email: string;
    full_name: string | null;
    role: string;
    is_active: boolean;
  };
  csrf_token: string;
  expires_at: string;
};
export type Round = { round: number; score: number; lessons: number; prompt: string };
export type Results = {
  log?: Round[];
  best_prompt?: string;
  test_score?: number;
  test_score_before?: number;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let csrfToken: string | null = null;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && (init?.method ?? "GET").toUpperCase() !== "GET") {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const r = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!r.ok) {
    let message = `Request failed (${r.status})`;
    try {
      const body: unknown = await r.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      }
    } catch {
      // Keep the status-based message for non-JSON errors.
    }
    throw new ApiError(message, r.status);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const classify = (text: string, trained: boolean) =>
  req<Classified>("/classify", {
    method: "POST",
    body: JSON.stringify({ text, use_memory: trained, use_best_prompt: trained }),
  });

export const sendFeedback = (text: string, predicted: string, correct: string) =>
  req<{ lesson?: string }>("/feedback", {
    method: "POST",
    body: JSON.stringify({ text, predicted, correct }),
  });

export async function getHawkeyeSession(): Promise<HawkeyeSession | null> {
  try {
    const session = await req<HawkeyeSession>("/auth/me");
    csrfToken = session.csrf_token;
    return session;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      csrfToken = null;
      return null;
    }
    throw error;
  }
}

export async function loginHawkeye(input: {
  organization_id: string;
  email: string;
  password: string;
}): Promise<HawkeyeSession> {
  const session = await req<HawkeyeSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  csrfToken = session.csrf_token;
  return session;
}

export async function logoutHawkeye(): Promise<void> {
  await req<void>("/auth/logout", { method: "POST" });
  csrfToken = null;
}

export async function sendChat(
  text: string,
  trained: boolean,
  filters?: AuditFilters,
): Promise<ChatResponse> {
  if (isAuditQuery(text) && !csrfToken && !(await getHawkeyeSession())) {
    throw new ApiError("Sign in as a Hawkeye Supervisor to view audit logs", 401);
  }
  return req<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      text,
      use_memory: trained,
      use_best_prompt: trained,
      ...(filters ? { filters } : {}),
    }),
  });
}

export function isAuditQuery(text: string): boolean {
  return (
    /\baudit(?:\s+(?:logs?|records?|trail|history))?\b/i.test(text) ||
    (/\buser[- ](?:created|generated|performed|made)\b|\b(?:created|generated|performed|made)\s+by\s+(?:a\s+)?users?\b|\bhuman[- ](?:created|generated|performed|made)\b|\bmanually\s+(?:created|generated|performed|made)\b/i.test(
      text,
    ) &&
      /\blogs?\b/i.test(text))
  );
}

export const getLessons = () => req<Lesson[]>("/lessons");

/** Returns null when training has not been run (404). */
export async function getResults(ensureBefore = false): Promise<Results | null> {
  const r = await fetch(`/api/results?ensure_before=${ensureBefore}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`Request failed (${r.status})`);
  return r.json();
}

export async function runTraining(): Promise<void> {
  const r = await fetch("/api/train", { method: "POST" });
  if (!r.ok) throw new Error(`Training failed (${r.status})`);
}
