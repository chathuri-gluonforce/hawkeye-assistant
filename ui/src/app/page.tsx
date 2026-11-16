"use client";
import { useEffect, useRef, useState } from "react";
import { classify, sendFeedback } from "@/lib/api";
import { GUIDE, LABELS, pretty } from "@/lib/labels";
import { useApp, type Msg } from "@/lib/store";
import { IntentBadge } from "@/components/IntentBadge";

const uid = () => Math.random().toString(36).slice(2);

export default function ChatPage() {
  const { trained, mode, messages, setMessages, refresh } = useApp();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const patch = (id: string, p: Partial<Msg>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...p } : m)));

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((p) => [...p, { id: uid(), role: "user", text }]);
    setBusy(true);
    try {
      const out = await classify(text, trained);
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
    } catch {
      setMessages((p) => [
        ...p,
        { id: uid(), role: "assistant", text: "I could not reach the API. Is uvicorn running on port 8000?", error: true },
      ]);
    }
    setBusy(false);
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
              Hello. Send a customer message and I will name the intent and point you to the right place.
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
            ) : (
              <div key={m.id} className="fade-in max-w-[85%] space-y-3 rounded-2xl rounded-bl-sm bg-zinc-100 px-4 py-3 dark:bg-zinc-800">
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
            placeholder="Type a customer message. Enter to send, Shift+Enter for a new line."
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
