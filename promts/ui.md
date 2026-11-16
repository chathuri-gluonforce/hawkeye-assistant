You are a senior front-end engineer. Build a production-quality chat UI for "Hawkeye Assistant", replacing the current Streamlit app.

## Scope
- Work ONLY inside a new `ui/` folder. Do not edit or read anything outside it, except the API contract below.
- Stack: Next.js (App Router) + React + TypeScript + Tailwind CSS. Use shadcn/ui (Radix) for components, TanStack Query for data fetching, and Zustand for state. No other heavy libraries.
- All pages are client-rendered (`"use client"`). The backend is a separate FastAPI service, so do not build server logic or API routes.
- API base URL comes from `NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8000`. Add a `rewrites()` rule in `next.config.ts` that proxies `/api/*` to the backend, so there are no CORS issues. The client calls `/api/...`.
- Include a `README.md` in `ui/` with run steps (`npm i && npm run dev`).

## Product
Hawkeye is a bank-reconciliation product. The assistant does NOT match records. It classifies the user's intent, then guides or warns. The UI must feel like a modern, polished AI chat product: clean, fast, and calm.

Intent labels: `upload_document`, `unmatched_items`, `amount_mismatch`, `recon_status`, `match_invoice`, `show_details`, `audit_query`, `other`.

## API contract (already exists, do not change)
- `POST /classify` body `{text, use_memory, use_best_prompt}` returns `{intent, prompt, lessons: [{lesson, score}]}`
- `POST /feedback` body `{text, predicted, correct}` returns `{lesson?}`
- `GET /lessons` returns `[{lesson, score}]`
- `GET /results?ensure_before=bool` returns `{log: [{round, score, lessons, prompt}], best_prompt, test_score, test_score_before?}`. A 404 means training has not been run.
- `POST /train` (long running, up to 15 minutes)

## Routes (App Router)
- `/` Chat (default)
- `/compare` Before vs After
- `/demo` Demo set
- `/training` Training results
- Shared layout in `app/layout.tsx` with the sidebar and theme provider.

## Screens
1. **Chat**
   - Message list with user and assistant bubbles, typing indicator, auto-scroll, and Enter to send (Shift+Enter for a newline).
   - Each assistant reply shows an intent badge (colour-coded per label) and a short guidance line telling the user where to go in the app (Ingestion Hub, Workbench, Reconcile, Audit log). `match_invoice` shows a clear warning that matching is not done in chat.
   - In Self-improving mode, show "Lessons used" in a collapsible section under the reply.
   - Under each reply, show Yes / No feedback. On No, show chips for the 8 labels. After the user picks one, show the lesson that was learned.
   - Mode switch in the header: Normal vs Self-improving. Show a warning if training has not been run.
2. **Before vs After**: one input, two side-by-side result cards (original prompt vs trained prompt + lessons). Optional "correct intent" selector that marks each card Right or Wrong.
3. **Demo set**: run a list of messages through both modes, with a progress bar, a results table with ✅/❌, and Before/After score metrics.
4. **Training**: line chart of score per round, before/after test score cards, expandable prompt per round, first vs best prompt, lessons table, and a "Run training" button with a long-running state.

## Layout
- Left sidebar: navigation, mode, and a live Lessons panel (sorted by score, refreshed after feedback or training).
- Responsive, with a collapsible sidebar on mobile.
- Dark and light theme with a toggle (next-themes). Default to the system theme.

## Quality bar
- Fully typed API client in `ui/src/lib/api/` with one function per endpoint.
- Loading skeletons (`loading.tsx` where useful), empty states, and clear error states (API unreachable, training missing).
- Accessible: keyboard navigation, focus rings, ARIA labels, and sufficient contrast.
- Subtle animation only (message fade-in, typing dots). No clutter.
- Small, reusable components. No file over ~200 lines.

## Deliverable
A working app I can start with `npm run dev` that talks to the running API. After you finish, list the files you created and anything that is unclear in the API.