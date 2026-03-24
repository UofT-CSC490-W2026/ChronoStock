"use client";

import { useRef } from "react";
import { NewsEvent } from "@/types";

interface EventPanelProps {
  events: NewsEvent[];
  activeEvent: NewsEvent | null;
  onCardHover: (event: NewsEvent | null, el: HTMLDivElement | null) => void;
  onCardClick: (event: NewsEvent) => void;
  expandedId: string | null;
}

const SENTIMENT_STYLES: Record<NewsEvent["sentiment"], string> = {
  positive: "border-green-500 bg-green-500/10",
  negative: "border-red-500 bg-red-500/10",
  neutral: "border-amber-500 bg-amber-500/10",
};

const SENTIMENT_DOT: Record<NewsEvent["sentiment"], string> = {
  positive: "bg-green-500",
  negative: "bg-red-500",
  neutral: "bg-amber-500",
};

const SENTIMENT_LABEL: Record<NewsEvent["sentiment"], string> = {
  positive: "text-green-400",
  negative: "text-red-400",
  neutral: "text-amber-400",
};

const SENTIMENT_TEXT: Record<NewsEvent["sentiment"], string> = {
  positive: "Positive",
  negative: "Negative",
  neutral: "Neutral",
};

export default function EventPanel({
  events,
  activeEvent,
  onCardHover,
  onCardClick,
  expandedId,
}: EventPanelProps) {
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  return (
    <div className="flex flex-col gap-2 pr-1">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1 shrink-0">
        Key Events
      </p>

      {events.length === 0 && (
        <p className="text-sm text-slate-600 mt-4">No events for this period.</p>
      )}

      {events.map((ev) => {
        const isActive = activeEvent?.id === ev.id;
        const isExpanded = expandedId === ev.id;

        return (
          <div
            key={ev.id}
            ref={(el) => { cardRefs.current[ev.id] = el; }}
            className={`rounded-xl border cursor-pointer transition-all duration-200 select-none
              ${SENTIMENT_STYLES[ev.sentiment]}
              ${isActive
                ? "ring-2 ring-indigo-400 shadow-lg shadow-indigo-500/20 opacity-100 scale-[1.01]"
                : "opacity-60 hover:opacity-90"
              }`}
            onMouseEnter={() => onCardHover(ev, cardRefs.current[ev.id])}
            onMouseLeave={() => onCardHover(null, null)}
            onClick={() => onCardClick(ev)}
          >
            {/* Card header — always visible */}
            <div className="px-3 pt-3 pb-2">
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`w-2 h-2 rounded-full shrink-0 ${SENTIMENT_DOT[ev.sentiment]}`} />
                <span className="text-[11px] text-slate-400 font-mono">{ev.time}</span>
                <span className={`text-[10px] font-semibold uppercase ml-auto ${SENTIMENT_LABEL[ev.sentiment]}`}>
                  {SENTIMENT_TEXT[ev.sentiment]}
                </span>
              </div>
              <p className="text-sm font-semibold text-slate-200 leading-snug">{ev.title}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">{ev.source}</p>
            </div>

            {/* Expand indicator */}
            <div className="px-3 pb-2 flex items-center gap-1 text-[11px] text-slate-600">
              <svg
                className={`w-3 h-3 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              <span>{isExpanded ? "Collapse" : "Read more"}</span>
            </div>

            {/* Expanded body */}
            {isExpanded && (
              <div className="px-3 pb-3 border-t border-white/10 pt-2">
                <p className="text-xs text-slate-300 leading-relaxed">{ev.summary}</p>
                {ev.url && (
                  <a
                    href={ev.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block mt-2 text-xs text-indigo-400 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Read full article →
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
