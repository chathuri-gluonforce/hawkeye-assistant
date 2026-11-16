"use client";
import { useCallback, useEffect, useState } from "react";
import { getResults, runTraining, type Results } from "@/lib/api";
import { useApp } from "@/lib/store";

const pct = (n?: number) => (n === undefined || n === null ? "—" : `${Math.round(n * 100)}%`);

export default function TrainingPage() {
  const { lessons, refresh } = useApp();
  const [results, setResults] = useState<Results | null>(null);
  const [state, setState] = useState<"loading" | "missing" | "error" | "ok">("loading");
  const [training, setTraining] = useState(false);
  const [scoring, setScoring] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getResults();
      setResults(r);
      setState(r ? "ok" : "missing");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const train = async () => {
    setTraining(true);
    try {
      await runTraining();
    } catch {}
    await load();
    await refresh();
    setTraining(false);
  };

  const computeBefore = async () => {
    setScoring(true);
    try {
      setResults(await getResults(true));
    } catch {}
    setScoring(false);
  };

  const log = results?.log ?? [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        {state === "loading" && <div className="h-24 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />}
        {state === "error" && <p className="text-sm text-red-600">Could not reach the API. Is uvicorn running?</p>}
        {state === "missing" && <p className="text-sm text-amber-600">No training run saved yet. Press Run training below.</p>}

        {state === "ok" && results && (
          <>
            {log.length > 0 && (
              <section>
                <h2 className="mb-2 font-semibold">Train score each round</h2>
                <Chart values={log.map((r) => r.score)} />
              </section>
            )}

            <section className="grid gap-4 sm:grid-cols-2">
              <Metric label="Test score before" value={pct(results.test_score_before)}>
                {results.test_score_before === undefined && (
                  <button onClick={computeBefore} disabled={scoring} className="mt-2 rounded-md bg-zinc-200 px-3 py-1 text-xs hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:hover:bg-zinc-700">
                    {scoring ? "Scoring…" : "Compute before score"}
                  </button>
                )}
              </Metric>
              <Metric label="Test score after" value={pct(results.test_score)} />
            </section>

            <section>
              <h2 className="mb-2 font-semibold">Prompt adjustments</h2>
              <div className="space-y-2">
                {log.map((r) => (
                  <details key={r.round} open={r.round === 1 || r.round === log.length} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                    <summary className="cursor-pointer text-sm">
                      Round {r.round} · score {pct(r.score)} · {r.lessons} lessons
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-600 dark:text-zinc-400">{r.prompt}</p>
                  </details>
                ))}
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <PromptBox title="First prompt" value={log[0]?.prompt ?? ""} />
              <PromptBox title="Best prompt" value={results.best_prompt ?? ""} />
            </section>
          </>
        )}

        <section>
          <h2 className="mb-2 font-semibold">Lessons in memory</h2>
          {!lessons?.length ? (
            <p className="text-sm text-zinc-500">No lessons yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-100 text-xs uppercase text-zinc-500 dark:bg-zinc-900">
                  <tr><th className="px-3 py-2">Lesson</th><th className="px-3 py-2">Score</th></tr>
                </thead>
                <tbody>
                  {lessons.slice().sort((a, b) => b.score - a.score).map((l, i) => (
                    <tr key={i} className="border-t border-zinc-200 dark:border-zinc-800">
                      <td className="px-3 py-2">{l.lesson}</td>
                      <td className="px-3 py-2">{l.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <button onClick={train} disabled={training} className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50">
            {training ? "Training… this can take several minutes" : "Run training"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-3xl font-semibold">{value}</div>
      {children}
    </div>
  );
}

function PromptBox({ title, value }: { title: string; value: string }) {
  return (
    <div>
      <div className="mb-1 text-sm font-medium">{title}</div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-100 p-3 text-xs dark:bg-zinc-900">{value}</pre>
    </div>
  );
}

function Chart({ values }: { values: number[] }) {
  const W = 600, H = 160, P = 24;
  const x = (i: number) => (values.length === 1 ? W / 2 : P + (i * (W - 2 * P)) / (values.length - 1));
  const y = (v: number) => H - P - v * (H - 2 * P);
  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-xl border border-zinc-200 p-2 dark:border-zinc-800" role="img" aria-label="Train score per round">
      {[0, 0.5, 1].map((g) => (
        <g key={g}>
          <line x1={P} x2={W - P} y1={y(g)} y2={y(g)} stroke="currentColor" opacity={0.12} />
          <text x={2} y={y(g) + 4} fontSize="10" fill="currentColor" opacity={0.5}>{Math.round(g * 100)}%</text>
        </g>
      ))}
      <polyline points={pts} fill="none" stroke="#0284c7" strokeWidth="2.5" />
      {values.map((v, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(v)} r="4" fill="#0284c7" />
          <text x={x(i)} y={H - 6} fontSize="10" textAnchor="middle" fill="currentColor" opacity={0.6}>{i + 1}</text>
        </g>
      ))}
    </svg>
  );
}
