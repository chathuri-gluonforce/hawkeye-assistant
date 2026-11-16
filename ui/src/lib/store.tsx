"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getLessons, getResults, type Lesson } from "./api";

export type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  intent?: string;
  lessons?: Lesson[];
  asked?: string;
  feedback?: "pending" | "asking" | "done";
  note?: string;
  error?: boolean;
};

type Mode = "normal" | "self";

type Ctx = {
  mode: Mode;
  setMode: (m: Mode) => void;
  ready: boolean;
  trained: boolean;
  messages: Msg[];
  setMessages: React.Dispatch<React.SetStateAction<Msg[]>>;
  lessons: Lesson[] | null;
  refresh: () => Promise<void>;
};

const AppCtx = createContext<Ctx | null>(null);

export function Providers({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("normal");
  const [ready, setReady] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [lessons, setLessons] = useState<Lesson[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLessons(await getLessons());
    } catch {
      setLessons(null);
    }
    try {
      setReady((await getResults()) !== null);
    } catch {
      setReady(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AppCtx.Provider
      value={{ mode, setMode, ready, trained: mode === "self" && ready, messages, setMessages, lessons, refresh }}
    >
      {children}
    </AppCtx.Provider>
  );
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside Providers");
  return c;
}
