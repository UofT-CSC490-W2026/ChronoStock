"use client";

import { useState } from "react";
import { StockNews } from "@/lib/api";

export default function NewsPanel({ news }: { news: StockNews[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (news.length === 0) {
    return <p className="text-sm text-slate-600">No recent news.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {news.map((item) => {
        const isExpanded = expandedId === item.id;
        return (
          <div
            key={item.id}
            className="rounded-xl border border-slate-700 bg-slate-800/50 cursor-pointer select-none hover:bg-slate-800 transition-colors overflow-hidden"
            onClick={() => setExpandedId(isExpanded ? null : item.id)}
          >
            {/* Thumbnail */}
            {item.thumbnail && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.thumbnail}
                alt=""
                className="w-full h-28 object-cover"
              />
            )}

            <div className="px-3 pt-3 pb-2">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[11px] font-mono text-slate-500">{item.time}</span>
                {item.publisher && (
                  <span className="text-[10px] text-slate-600 ml-auto truncate max-w-[120px]">
                    {item.publisher}
                  </span>
                )}
              </div>
              <p className="text-sm font-medium text-slate-200 leading-snug">{item.title}</p>
            </div>

            <div className="px-3 pb-2 flex items-center gap-1 text-[11px] text-slate-600">
              <svg
                className={`w-3 h-3 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              <span>{isExpanded ? "Collapse" : "Read more"}</span>
            </div>

            {isExpanded && (
              <div className="px-3 pb-3 border-t border-white/10 pt-2">
                {item.summary && (
                  <p className="text-xs text-slate-300 leading-relaxed mb-2">{item.summary}</p>
                )}
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block text-xs text-indigo-400 hover:underline"
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
