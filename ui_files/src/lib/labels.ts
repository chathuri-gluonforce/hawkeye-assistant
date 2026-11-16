export const LABELS = [
  "upload_document",
  "unmatched_items",
  "amount_mismatch",
  "recon_status",
  "match_invoice",
  "show_details",
  "audit_query",
  "other",
] as const;

const PRETTY: Record<string, string> = {
  upload_document: "Upload document",
  unmatched_items: "Unmatched items",
  amount_mismatch: "Amount mismatch",
  recon_status: "Recon status",
  match_invoice: "Match invoice",
  show_details: "Show details",
  audit_query: "Audit log",
  other: "Other",
};

export const pretty = (l: string) => PRETTY[l] ?? l;

export const COLORS: Record<string, string> = {
  upload_document: "bg-sky-600",
  unmatched_items: "bg-amber-600",
  amount_mismatch: "bg-orange-600",
  recon_status: "bg-emerald-600",
  match_invoice: "bg-red-600",
  show_details: "bg-violet-600",
  audit_query: "bg-slate-600",
  other: "bg-zinc-500",
};

export const GUIDE: Record<string, string> = {
  upload_document: "Go to the Ingestion Hub to import invoices or bank statements.",
  unmatched_items: "Open Reconcile and filter to Unmatched / Outstanding items.",
  amount_mismatch:
    "There is an amount gap. Keep it as an outstanding item (not a posted match) and review it in the Workbench.",
  recon_status: "Open Reconcile to see progress, and use the status filters.",
  match_invoice: "Matching is not done in chat. Use the Workbench / Reconcile to match.",
  show_details:
    "Open the ledger row, the Workbench candidate pane, the outstanding item, or the match under MATCHED.",
  audit_query: "Open the Audit log to see who did what.",
  other: "I can help with uploads, unmatched items, recon status, item details and audit questions.",
};
