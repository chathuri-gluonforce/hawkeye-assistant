"use client";
import { useState } from "react";
import { classify } from "@/lib/api";
import { LABELS, pretty } from "@/lib/labels";
import { useApp } from "@/lib/store";

type Row = { text: string; correct?: string; before: string; after: string };

const SAMPLE = `unmatched_items | what is still outstanding?
match_invoice | please match INV-102 to this bank line
audit_query | who changed this match yesterday?`;

export default function DemoPage() {
  const { ready } = useApp();
  const [raw, setRaw] = useState(SAMPLE);
  const [rows, setRows] = useState<Row[]>([]);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const parse = () =>
    raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [a, ...rest] = l.split("|");
        const label = a.trim();
        return rest.length && (LABELS as readonly string[]).includes(label)
          ? { text: rest.join("|").trim(), correct: label }
          : { text: l, correct: undefined };
      });

  const run = async () => {
    const items = parse();
    setBusy(true);
    setErr("");
    setRows([]);
    const out: Row[] = [];
    try {
      for (let i = 0; i < items.length; i++) {
        const b = await classify(items[i].text, false);
        const a = await classify(items[i].text, true);
        out.push({ ...items[i], before: b.intent, after: a.intent });
        setProgress((i + 1) / items.length);
      }
    } catch {
      setErr("Demo failed. Is the API running?");
    }
    setRows(out);
    setBusy(false);
  };

  const scored = rows.filter((r) => r.correct);
  const bOk = scored.filter((r) => r.before === r.correct).length;
  const aOk = scored.filter((r) => r.after === r.correct).length;
  const mark = (p: string, c?: string) => (c ? `${p === c ? "✅" : "❌"} ${pretty(p)}` : pretty(p));

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <p className="text-sm text-zinc-500">
          One message per line. Use <code>label | message</code> to score it, or just the message.
        </p>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={6}
          aria-label="Demo messages"
          className="w-full rounded-lg border border-zinc-300 bg-transparent p-3 font-mono text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-zinc-700"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={run}
            disabled={busy || !ready || !raw.trim()}
            className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {busy ? "Running…" : "Run demo"}
          </button>
          {!ready && <span className="text-sm text-amber-600">Run training first.</span>}
          {busy && (
            <div className="h-2 w-48 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div className="h-full bg-sky-600 transition-all" style={{ width: `${progress * 100}%` }} />
            </div>
          )}
        </div>
        {err && <p className="text-sm text-red-600">{err}</p>}

        {rows.length > 0 && (
          <div className="fade-in space-y-4">
            {scored.length > 0 && (
              <div className="grid grid-cols-2 gap-4">
                <Metric label="Before" value={`${bOk}/${scored.length} correct`} />
                <Metric label="After" value={`${aOk}/${scored.length} correct`} />
              </div>
            )}
            <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-100 text-xs uppercase text-zinc-500 dark:bg-zinc-900">
                  <tr>
                    {["Message", "Correct", "Before", "After"].map((h) => (
                      <th key={h} className="px-3 py-2">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-zinc-200 dark:border-zinc-800">
                      <td className="px-3 py-2">{r.text}</td>
                      <td className="px-3 py-2">{r.correct ? pretty(r.correct) : "—"}</td>
                      <td className="px-3 py-2">{mark(r.before, r.correct)}</td>
                      <td className="px-3 py-2">{mark(r.after, r.correct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
