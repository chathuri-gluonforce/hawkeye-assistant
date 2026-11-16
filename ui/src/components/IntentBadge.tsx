import { COLORS, pretty } from "@/lib/labels";

export function IntentBadge({ intent, verdict }: { intent: string; verdict?: "right" | "wrong" }) {
  const bg = verdict === "right" ? "bg-green-700" : verdict === "wrong" ? "bg-red-700" : COLORS[intent] ?? "bg-zinc-500";
  const prefix = verdict === "right" ? "Right · " : verdict === "wrong" ? "Wrong · " : "";
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-xs font-semibold text-white ${bg}`}>
      {prefix}
      {pretty(intent)}
    </span>
  );
}
