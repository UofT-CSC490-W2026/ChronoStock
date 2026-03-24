"use client";

import { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import {
  createChart,
  IChartApi,
  LineSeries,
  ColorType,
  createSeriesMarkers,
  Time,
} from "lightweight-charts";
import { OHLCBar, NewsEvent } from "@/types";

export const STOCK_COLORS = ["#818cf8", "#34d399", "#fbbf24", "#fb7185", "#22d3ee"];

export interface CompareStock {
  ticker: string;
  bars: OHLCBar[];
  color: string;
  events: NewsEvent[];
}

interface CompareChartProps {
  stocks: CompareStock[];
  visibleEventTickers: Set<string>;
  normalized: boolean;
  onViewChange?: () => void;
}

export interface CompareChartHandle {
  getXForTime: (time: string) => number | null;
}

const SENTIMENT_COLOR: Record<NewsEvent["sentiment"], string> = {
  positive: "#22c55e",
  negative: "#ef4444",
  neutral: "#f59e0b",
};

function toNormalized(bars: OHLCBar[]): { time: Time; value: number }[] {
  if (!bars.length) return [];
  const base = bars[0].close;
  return bars.map((b) => ({
    time: b.time as Time,
    value: parseFloat((((b.close - base) / base) * 100).toFixed(4)),
  }));
}

function toRaw(bars: OHLCBar[]): { time: Time; value: number }[] {
  return bars.map((b) => ({ time: b.time as Time, value: b.close }));
}

const CompareChart = forwardRef<CompareChartHandle, CompareChartProps>(
  ({ stocks, visibleEventTickers, normalized, onViewChange }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);

    useImperativeHandle(ref, () => ({
      getXForTime: (time: string) =>
        chartRef.current?.timeScale().timeToCoordinate(time as Time) ?? null,
    }));

    useEffect(() => {
      if (!containerRef.current) return;

      const chart = createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "#0f172a" },
          textColor: "#94a3b8",
        },
        grid: {
          vertLines: { color: "#1e293b" },
          horzLines: { color: "#1e293b" },
        },
        crosshair: {
          vertLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
          horzLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
        },
        rightPriceScale: { borderColor: "#1e293b" },
        timeScale: { borderColor: "#1e293b", timeVisible: true },
        localization: {
          priceFormatter: normalized
            ? (p: number) => `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`
            : (p: number) => `$${p.toFixed(2)}`,
        },
      });

      chartRef.current = chart;

      for (const stock of stocks) {
        const series = chart.addSeries(LineSeries, {
          color: stock.color,
          lineWidth: 2,
          crosshairMarkerVisible: true,
          crosshairMarkerRadius: 4,
          crosshairMarkerBorderColor: stock.color,
          crosshairMarkerBackgroundColor: "#0f172a",
          title: stock.ticker,
        });

        series.setData(normalized ? toNormalized(stock.bars) : toRaw(stock.bars));

        // Add this stock's events if its ticker is in the visible set
        if (visibleEventTickers.has(stock.ticker) && stock.events.length > 0) {
          const markers = stock.events.map((ev) => ({
            time: ev.time as Time,
            position: "aboveBar" as const,
            color: SENTIMENT_COLOR[ev.sentiment],
            shape: ev.sentiment === "negative" ? ("arrowDown" as const) : ("arrowUp" as const),
            text: `[${stock.ticker}] ${ev.title.length > 18 ? ev.title.slice(0, 18) + "…" : ev.title}`,
            size: 1,
          }));
          createSeriesMarkers(series, markers);
        }
      }

      requestAnimationFrame(() => {
        chart.timeScale().fitContent();
        onViewChange?.();
      });

      if (onViewChange) {
        chart.timeScale().subscribeVisibleLogicalRangeChange(onViewChange);
      }

      return () => chart.remove();
    }, [stocks, visibleEventTickers, normalized, onViewChange]);

    return <div ref={containerRef} className="w-full h-full" />;
  }
);
CompareChart.displayName = "CompareChart";
export default CompareChart;
