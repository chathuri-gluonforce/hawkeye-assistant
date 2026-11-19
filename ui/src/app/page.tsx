"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  getHawkeyeSession,
  isAuditQuery,
  loginHawkeye,
  sendChat,
  sendFeedback,
  type ChatResponse,
} from "@/lib/api";
import { GUIDE, LABELS, pretty } from "@/lib/labels";
import { useApp, type Msg } from "@/lib/store";
import { IntentBadge } from "@/components/IntentBadge";

const uid = () => Math.random().toString(36).slice(2);

export default function ChatPage() {
  const { trained, mode, messages, setMessages, refresh } = useApp();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingAuditQuery, setPendingAuditQuery] = useState<string | null>(null);
  const [organizationId, setOrganizationId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const patch = (id: string, p: Partial<Msg>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...p } : m)));

  const addChatResponse = (text: string, out: ChatResponse) => {
    if (out.kind === "audit_results") {
      setMessages((p) => [
        ...p,
        {
          id: uid(),
          role: "assistant",
          text,
          asked: text,
          intent: "audit_query",
          auditResult: out.result,
        },
      ]);
      return;
    }

    setMessages((p) => [
      ...p,
      {
        id: uid(),
        role: "assistant",
        text,
        asked: text,
        intent: out.intent,
        lessons: out.lessons ?? [],
        feedback: mode === "self" ? "pending" : undefined,
      },
    ]);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((p) => [...p, { id: uid(), role: "user", text }]);
    setBusy(true);
    try {
      addChatResponse(text, await sendChat(text, trained));
    } catch (error) {
      let requestError: unknown = error;
      if (error instanceof ApiError && error.status === 403) {
        try {
          if (await getHawkeyeSession()) {
            addChatResponse(text, await sendChat(text, trained));
            return;
          }
          requestError = new ApiError(
            "Sign in with a Hawkeye Supervisor account to view audit logs",
            401,
          );
        } catch (sessionError) {
          requestError = sessionError;
        }
      }

      if (requestError instanceof ApiError && requestError.status === 401) {
        setPendingAuditQuery(text);
        setLoginError("");
        setMessages((p) => [
          ...p,
          {
            id: uid(),
            role: "assistant",
            text: "Sign in with a Hawkeye Supervisor account to view audit logs.",
            loginPrompt: true,
          },
        ]);
      } else {
        setMessages((p) => [
          ...p,
          {
            id: uid(),
            role: "assistant",
            text: requestError instanceof Error ? requestError.message : "The request failed.",
            error: true,
          },
        ]);
      }
    } finally {
      setBusy(false);
    }
  };

  const connectAndRetry = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!pendingAuditQuery || busy) return;
    setBusy(true);
    setLoginError("");
    try {
      await loginHawkeye({
        organization_id: organizationId.trim(),
        email: email.trim(),
        password,
      });
      const query = pendingAuditQuery;
      const filters = isAuditQuery(query) ? undefined : { page: 1, page_size: 20 };
      const result = await sendChat(query, trained, filters);
      setMessages((prev) =>
        prev.map((message) =>
          message.loginPrompt
            ? {
                ...message,
                text: "Connected. Here are the audit records you requested.",
                loginPrompt: false,
              }
            : message,
        ),
      );
      setPendingAuditQuery(null);
      setPassword("");
      addChatResponse(query, result);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  const changeAuditPage = async (message: Msg, page: number) => {
    if (!message.auditResult || !message.asked || busy) return;
    setBusy(true);
    try {
      const result = await sendChat(message.asked, trained, {
        ...message.auditResult.filters,
        page,
      });
      if (result.kind === "audit_results") {
        patch(message.id, { auditResult: result.result });
      }
    } catch (error) {
      patch(message.id, {
        note: error instanceof Error ? error.message : "Could not load that page.",
      });
    } finally {
      setBusy(false);
    }
  };

  const yes = async (m: Msg) => {
    patch(m.id, { feedback: "done", note: "Thanks. No new lesson was needed." });
    try {
      await sendFeedback(m.asked!, m.intent!, m.intent!);
      refresh();
    } catch {
      patch(m.id, { note: "Could not save feedback." });
    }
  };

  const fix = async (m: Msg, label: string) => {
    patch(m.id, { feedback: "done", note: `Got it. You meant ${pretty(label)}.` });
    try {
      const out = await sendFeedback(m.asked!, m.intent!, label);
      patch(m.id, {
        note: `Got it. You meant ${pretty(label)}.${out.lesson ? ` I learned: ${out.lesson}` : ""}`,
      });
      refresh();
    } catch {
      patch(m.id, { note: "Could not save feedback." });
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.length === 0 && (
            <div className="rounded-xl border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
              Send a customer message for intent guidance, or ask to view existing Hawkeye audit logs.
            </div>
          )}

          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="fade-in ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-sky-600 px-4 py-2 text-white">
                {m.text}
              </div>
            ) : m.error ? (
              <div key={m.id} className="fade-in max-w-[80%] rounded-2xl bg-red-100 px-4 py-2 text-sm text-red-900 dark:bg-red-900/30 dark:text-red-200">
                {m.text}
              </div>
            ) : m.auditResult ? (
              <div key={m.id} className="fade-in max-w-[90%] space-y-3 rounded-2xl rounded-bl-sm bg-zinc-100 px-4 py-3 dark:bg-zinc-800">
                <IntentBadge intent="audit_query" />
                <p className="text-sm">{m.auditResult.answer}</p>
                {m.auditResult.filters.automated_only !== undefined &&
                  m.auditResult.filters.automated_only !== null && (
                  <p className="text-xs text-zinc-500">
                    Filter: {m.auditResult.filters.automated_only === false
                      ? "User-performed"
                      : m.auditResult.filters.automated_only === true
                        ? "Automated"
                        : ""}
                  </p>
                )}
                <div className="space-y-2">
                  {m.auditResult.records.map((record) => (
                    <details key={record.id} className="rounded-lg border border-zinc-300 p-3 text-sm dark:border-zinc-700">
                      <summary className="cursor-pointer">
                        <span className="font-medium">{record.action}</span>
                        <span className="text-zinc-500"> · {new Date(record.created_at).toLocaleString()}</span>
                        <span className="block text-xs text-zinc-500">
                          {record.automated ? "Automated" : record.actor_name ?? record.actor_email ?? "Unknown actor"}
                        </span>
                      </summary>
                      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                        <dt className="text-zinc-500">Entity</dt>
                        <dd>{record.entity_type}{record.entity_id ? ` · ${record.entity_id}` : ""}</dd>
                        <dt className="text-zinc-500">Actor</dt>
                        <dd>{record.actor_email ?? record.actor_name ?? (record.automated ? "Automated" : "Unknown")}</dd>
                      </dl>
                      {Object.keys(record.details).length > 0 && (
                        <ul className="mt-2 space-y-1 text-xs">
                          {Object.entries(record.details).map(([key, value]) => (
                            <li key={key}>
                              <span className="text-zinc-500">{key}: </span>
                              {typeof value === "string" ? value : JSON.stringify(value)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </details>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs">
                  <button
                    onClick={() => changeAuditPage(m, m.auditResult!.page - 1)}
                    disabled={busy || m.auditResult.page <= 1}
                    className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
                  >
                    Previous
                  </button>
                  <span>Page {m.auditResult.page}</span>
                  <button
                    onClick={() => changeAuditPage(m, m.auditResult!.page + 1)}
                    disabled={busy || !m.auditResult.has_more}
                    className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
                  >
                    Next
                  </button>
                </div>
                {m.note && <p className="text-xs text-red-600">{m.note}</p>}
              </div>
            ) : (
              <div key={m.id} className="fade-in max-w-[85%] space-y-3 rounded-2xl rounded-bl-sm bg-zinc-100 px-4 py-3 dark:bg-zinc-800">
                {m.loginPrompt ? (
                  <>
                    <p className="text-sm">{m.text}</p>
                    <form onSubmit={connectAndRetry} className="space-y-2">
                      <label className="block text-xs">
                        Hawkeye organization ID
                        <input
                          required
                          value={organizationId}
                          onChange={(event) => setOrganizationId(event.target.value)}
                          autoComplete="organization"
                          className="mt-1 w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
                        />
                      </label>
                      <label className="block text-xs">
                        Email
                        <input
                          required
                          type="email"
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          autoComplete="username"
                          className="mt-1 w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
                        />
                      </label>
                      <label className="block text-xs">
                        Password
                        <input
                          required
                          type="password"
                          value={password}
                          onChange={(event) => setPassword(event.target.value)}
                          autoComplete="current-password"
                          className="mt-1 w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
                        />
                      </label>
                      {loginError && <p role="alert" className="text-xs text-red-600">{loginError}</p>}
                      <button
                        type="submit"
                        disabled={busy}
                        className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                      >
                        {busy ? "Connecting…" : "Connect and show logs"}
                      </button>
                    </form>
                  </>
                ) : (
                  <>
                    <IntentBadge intent={m.intent!} />
                    {m.intent === "match_invoice" ? (
                      <p className="rounded-md bg-red-100 p-2 text-sm text-red-900 dark:bg-red-900/30 dark:text-red-200">
                        ⚠ {GUIDE.match_invoice}
                      </p>
                    ) : (
                      <p className="text-sm">{GUIDE[m.intent!]}</p>
                    )}

                    {mode === "self" && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-zinc-500">
                          Lessons used ({m.lessons?.length ?? 0})
                        </summary>
                        <ul className="mt-1 space-y-1">
                          {(m.lessons ?? []).length === 0 && <li className="text-zinc-500">No similar lessons retrieved.</li>}
                          {m.lessons?.map((l, i) => (
                            <li key={i}>
                              {l.lesson} <span className="text-zinc-500">(score {l.score})</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    {m.feedback === "pending" && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-zinc-500">Is that right?</span>
                        <button onClick={() => yes(m)} className="rounded-md bg-green-600 px-3 py-1 text-white hover:bg-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-400">
                          Yes
                        </button>
                        <button onClick={() => patch(m.id, { feedback: "asking" })} className="rounded-md bg-zinc-300 px-3 py-1 hover:bg-zinc-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:bg-zinc-700 dark:hover:bg-zinc-600">
                          No
                        </button>
                      </div>
                    )}
                    {m.feedback === "asking" && (
                      <div>
                        <div className="mb-1 text-xs text-zinc-500">What did you mean?</div>
                        <div className="flex flex-wrap gap-1">
                          {LABELS.map((l) => (
                            <button key={l} onClick={() => fix(m, l)} className="rounded-full border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-zinc-600 dark:hover:bg-zinc-700">
                              {pretty(l)}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {m.feedback === "done" && m.note && <p className="text-xs text-zinc-500">{m.note}</p>}
                  </>
                )}
              </div>
            )
          )}

          {busy && (
            <div className="fade-in flex w-16 justify-center gap-1 rounded-2xl bg-zinc-100 px-4 py-3 dark:bg-zinc-800" aria-label="Typing">
              {[0, 1, 2].map((i) => (
                <span key={i} className="dot h-2 w-2 rounded-full bg-zinc-500" style={{ animationDelay: `${i * 0.2}s` }} />
              ))}
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <div className="border-t border-zinc-200 p-4 dark:border-zinc-800">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Ask a question or request audit logs. Enter to send, Shift+Enter for a new line."
            aria-label="Message"
            className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-zinc-300 bg-transparent px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-zinc-700"
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="h-11 rounded-xl bg-sky-600 px-5 text-sm font-medium text-white hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
