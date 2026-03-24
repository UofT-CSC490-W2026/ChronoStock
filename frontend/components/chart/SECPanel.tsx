"use client";

import { useState } from "react";
import { ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import { SECFiling } from "@/lib/api";

interface Props {
  filings: SECFiling[];
}

export default function SECPanel({ filings }: Props) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [expanded, setExpanded] = useState<"8-K" | "4" | null>(null);

  if (!filings.length) return null;

  const filings8K = filings.filter((f) => f.form === "8-K");
  const filings4  = filings.filter((f) => f.form === "4");

  const Section = ({
    form,
    label,
    color,
    items,
  }: {
    form: "8-K" | "4";
    label: string;
    color: string;
    items: SECFiling[];
  }) => {
    if (!items.length) return null;
    const open = expanded === form;
    return (
      <div className="mx-4 mb-3 border border-slate-700/60 rounded-xl overflow-hidden bg-slate-800/30">
        <button
          onClick={() => setExpanded(open ? null : form)}
          className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-slate-800/80 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded-md"
              style={{ backgroundColor: color + "22", color, border: `1px solid ${color}44` }}
            >
              {form}
            </span>
            <span className="text-xs font-medium text-slate-300">{label}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-medium text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700/50">
              {items.length}
            </span>
            {open ? (
              <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
            )}
          </div>
        </button>

        {open && (
          <div className="border-t border-slate-700/60 max-h-60 overflow-y-auto bg-slate-900/50">
            {items.map((f, i) => (
              <a
                key={i}
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2.5 px-3 py-2.5 border-b border-slate-800/50 last:border-0 hover:bg-slate-800 transition-colors group"
              >
                <span className="text-[10px] text-slate-500 font-mono mt-[2px] shrink-0 w-[68px]">
                  {f.date}
                </span>
                <span className="text-[11px] text-slate-400 group-hover:text-slate-200 flex-1 leading-snug transition-colors">
                  {f.label}
                </span>
                <ExternalLink
                  className="w-3 h-3 text-slate-600 group-hover:text-indigo-400 shrink-0 mt-[2px] transition-colors"
                />
              </a>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="border-b border-slate-800">
      <button
        onClick={() => setPanelOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-900/50 transition-colors"
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          SEC Filing Details
        </span>
        {panelOpen ? (
          <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        )}
      </button>

      {panelOpen && (
        <div className="pb-1">
          <Section form="8-K" label="Corporate Events"     color="#6366f1" items={filings8K} />
          <Section form="4"   label="Insider Transactions" color="#f97316" items={filings4}  />
        </div>
      )}
    </div>
  );
}
