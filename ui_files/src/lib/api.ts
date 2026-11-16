export type Lesson = { lesson: string; score: number };
export type Classified = { intent: string; prompt?: string; lessons?: Lesson[] };
export type Round = { round: number; score: number; lessons: number; prompt: string };
export type Results = {
  log?: Round[];
  best_prompt?: string;
  test_score?: number;
  test_score_before?: number;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`Request failed (${r.status})`);
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
