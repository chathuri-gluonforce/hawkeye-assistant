"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/lib/store";

const NAV = [
  { href: "/", label: "Chat" },
  { href: "/compare", label: "Before vs After" },
  { href: "/demo", label: "Demo set" },
  { href: "/training", label: "Training" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { mode, setMode, ready, lessons, lessonsLoading, lessonsError } = useApp();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);
  useEffect(() => setOpen(false), [path]);

  const toggleTheme = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {}
    setDark(next);
  };

  const modeBtn = (m: "normal" | "self", label: string) => (
    <button
      onClick={() => setMode(m)}
      aria-pressed={mode === m}
      className={`flex-1 rounded-md px-2 py-1.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
        mode === m ? "bg-sky-600 text-white" : "bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex h-dvh bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {open && <div className="fixed inset-0 z-20 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-72 flex-col gap-4 border-r border-zinc-200 bg-zinc-50 p-4 transition-transform dark:border-zinc-800 dark:bg-zinc-900 md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div>
          <div className="text-lg font-semibold">Hawkeye Assistant</div>
          <div className="text-xs text-zinc-500">Self-improving intent agent</div>
        </div>

        <nav className="flex flex-col gap-1" aria-label="Main">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`rounded-md px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
                path === n.href
                  ? "bg-zinc-200 font-medium dark:bg-zinc-800"
                  : "hover:bg-zinc-100 dark:hover:bg-zinc-800/60"
              }`}
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">Agent</div>
          <div className="flex gap-1">
            {modeBtn("normal", "Normal")}
            {modeBtn("self", "Self-improving")}
          </div>
          {mode === "self" && !ready && (
            <p className="mt-2 rounded-md bg-amber-100 p-2 text-xs text-amber-900 dark:bg-amber-900/30 dark:text-amber-200">
              Run training first. Until then the original prompt is used.
            </p>
          )}
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">Lessons</div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {lessonsLoading && <p className="text-xs text-zinc-500">Loading memory...</p>}
            {!lessonsLoading && lessonsError && (
              <p className="text-xs text-red-600">Memory unavailable: {lessonsError}</p>
            )}
            {!lessonsLoading && !lessonsError && lessons?.length === 0 && (
              <p className="text-xs text-zinc-500">No lessons yet.</p>
            )}
            {lessons
              ?.slice()
              .sort((a, b) => b.score - a.score)
              .map((l, i) => (
                <div key={i} className="rounded-md bg-white p-2 text-xs shadow-sm dark:bg-zinc-800">
                  <div>{l.lesson}</div>
                  <div className="mt-1 text-zinc-500">score: {l.score}</div>
                </div>
              ))}
          </div>
        </div>

        <button
          onClick={toggleTheme}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {dark ? "Light theme" : "Dark theme"}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-zinc-200 px-4 dark:border-zinc-800">
          <button
            className="rounded-md border border-zinc-300 px-2 py-1 text-sm md:hidden dark:border-zinc-700"
            onClick={() => setOpen(true)}
            aria-label="Open menu"
          >
            ☰
          </button>
          <div className="font-medium">{NAV.find((n) => n.href === path)?.label ?? ""}</div>
          <span className="ml-auto rounded-full bg-zinc-100 px-3 py-1 text-xs dark:bg-zinc-800">
            {mode === "self" ? "Self-improving" : "Normal"}
          </span>
        </header>
        <main className="min-h-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
