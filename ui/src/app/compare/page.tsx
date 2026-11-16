"use client";
import { useState } from "react";
import { classify, type Classified } from "@/lib/api";
import { LABELS, pretty } from "@/lib/labels";
import { useApp } from "@/lib/store";
import { IntentBadge } from "@/components/IntentBadge";

type Shown = { before: Classified; after: Classified | null };

export default function ComparePage() {
  const { ready } = useApp();
  const [text, setText] = useState("");
  const [correct, setCorrect] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);

  const run = async () => {
    setBusy(true);
    setErr("");
    try {
      const before = await classify(text.trim(), false);
      const after = ready ? await classify(text.trim(), true) : null;
      setShown({ before, after });
    } catch {
      setErr("Could not reach the API. Is uvicorn running?");
    }
    setBusy(false);
  };

  const verdict = (i: string) => (correct ? (i === correct ? "right" : "wrong") : undefined);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <p className="text-sm text-zinc-500">
          Before uses the original prompt and no lessons. After uses the trained prompt and similar lessons.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type a hard message"
            aria-label="Customer message"
            className="min-w-64 flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-zinc-700"
          />
          <select
            value={correct}
            onChange={(e) => setCorrect(e.target.value)}
            aria-label="Correct intent"
            className="rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          >
            <option value="">Correct intent: not set</option>
            {LABELS.map((l) => (
              <option key={l} value={l}>
                {pretty(l)}
              </option>
            ))}
          </select>
          <button
            onClick={run}
            disabled={busy || !text.trim()}
            className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {busy ? "Classifying…" : "Classify"}
          </button>
        </div>
        {err && <p className="text-sm text-red-600">{err}</p>}

        {shown && (
          <div className="fade-in grid gap-4 md:grid-cols-2">
            <Card title="Before" sub="Default prompt. No memory.">
              <IntentBadge intent={shown.before.intent} verdict={verdict(shown.before.intent)} />
              <Prompt value={shown.before.prompt} />
            </Card>
            <Card title="After" sub="Trained prompt. Lessons retrieved.">
              {shown.after === null ? (
                <p className="text-sm text-amber-600">Run training first.</p>
              ) : (
                <>
                  <IntentBadge intent={shown.after.intent} verdict={verdict(shown.after.intent)} />
                  <Prompt value={shown.after.prompt} />
                  <div className="text-sm font-medium">Lessons used</div>
                  {(shown.after.lessons ?? []).length === 0 && (
                    <p className="text-xs text-zinc-500">No similar lessons retrieved.</p>
                  )}
                  {shown.after.lessons?.map((l, i) => (
                    <p key={i} className="text-xs">
                      {l.lesson} <span className="text-zinc-500">(score {l.score})</span>
                    </p>
                  ))}
                </>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="text-xs text-zinc-500">{sub}</p>
      </div>
      {children}
    </section>
  );
}

function Prompt({ value }: { value?: string }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-zinc-500">Prompt</summary>
      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-zinc-100 p-2 dark:bg-zinc-900">
        {value ?? ""}
      </pre>
    </details>
  );
}
