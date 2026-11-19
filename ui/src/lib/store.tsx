"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  getLessons,
  getResults,
  type AuditResult,
  type Lesson,
} from "./api";

export type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  intent?: string;
  lessons?: Lesson[];
  auditResult?: AuditResult;
  loginPrompt?: boolean;
  loginError?: string;
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
  lessonsLoading: boolean;
  lessonsError: string | null;
  refresh: () => Promise<void>;
};

const AppCtx = createContext<Ctx | null>(null);

export function Providers({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("normal");
  const [ready, setReady] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [lessons, setLessons] = useState<Lesson[] | null>(null);
  const [lessonsLoading, setLessonsLoading] = useState(true);
  const [lessonsError, setLessonsError] = useState<string | null>(null);

  const fetchLessons = useCallback(async (): Promise<{
    lessons: Lesson[] | null;
    error: string | null;
  }> => {
    try {
      return { lessons: await getLessons(), error: null };
    } catch (error) {
      return {
        lessons: null,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }, []);

  const fetchReady = useCallback(async () => {
    try {
      return (await getResults()) !== null;
    } catch {
      return false;
    }
  }, []);

  const refresh = useCallback(async () => {
    setLessonsLoading(true);
    setLessonsError(null);
    const lessonRequest = fetchLessons().then(({ lessons: result, error }) => {
      setLessons(result);
      setLessonsError(error);
      setLessonsLoading(false);
    });
    const resultsRequest = fetchReady().then(setReady);
    await Promise.all([lessonRequest, resultsRequest]);
  }, [fetchLessons, fetchReady]);

  useEffect(() => {
    fetchLessons().then(({ lessons: result, error }) => {
      setLessons(result);
      setLessonsError(error);
      setLessonsLoading(false);
    });
    fetchReady().then(setReady);
  }, [fetchLessons, fetchReady]);

  return (
    <AppCtx.Provider
      value={{
        mode,
        setMode,
        ready,
        trained: mode === "self" && ready,
        messages,
        setMessages,
        lessons,
        lessonsLoading,
        lessonsError,
        refresh,
      }}
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
