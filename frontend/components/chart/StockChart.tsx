"use client";

import { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  AreaSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  createSeriesMarkers,
  Time,
} from "lightweight-charts";
import { OHLCBar, NewsEvent } from "@/types";

export interface StockChartHandle {
  getXForTime: (time: string) => number | null;
  /** Returns pixel coords (relative to chart container) for a date + price value */
  getPositionForDate: (date: string, price: number) => { x: number; y: number } | null;
}

interface MovingAverageSeries {
  period: number;
  color: string;
  data: { time: string; value: number }[];
}

interface StockChartProps {
  bars: OHLCBar[];
  events: NewsEvent[];
  activeEventTime: string | null;
  onChartEventHover: (event: NewsEvent | null) => void;
  /** Fires whenever the visible range changes (pan / zoom / resize) */
  onViewChange?: () => void;
  movingAverages?: MovingAverageSeries[];
}

const SENTIMENT_COLOR: Record<NewsEvent["sentiment"], string> = {
  positive: "#22c55e",
  negative: "#ef4444",
  neutral: "#f59e0b",
};

const StockChart = forwardRef<StockChartHandle, StockChartProps>(
  ({ bars, events, activeEventTime, onChartEventHover, onViewChange, movingAverages }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const seriesRef = useRef<ISeriesApi<any> | null>(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const volumeSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const maSeriesRef = useRef<ISeriesApi<"Line">[]>([]);
    const highlightRef = useRef<HTMLDivElement>(null);
    const onHoverRef = useRef(onChartEventHover);
    onHoverRef.current = onChartEventHover;
    const onViewChangeRef = useRef(onViewChange);
    onViewChangeRef.current = onViewChange;

    useImperativeHandle(ref, () => ({
      getXForTime: (time: string) =>
        chartRef.current?.timeScale().timeToCoordinate(time as Time) ?? null,

      getPositionForDate: (date: string, price: number) => {
        if (!chartRef.current || !seriesRef.current) return null;
        const x = chartRef.current.timeScale().timeToCoordinate(date as Time);
        const y = seriesRef.current.priceToCoordinate(price);
        if (x === null || y === null) return null;
        return { x, y };
      },
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
          vertLines: { visible: false },
          horzLines: { visible: false },
        },
        crosshair: {
          vertLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
          horzLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
        },
        rightPriceScale: { borderColor: "#1e293b" },
        timeScale: { borderColor: "#1e293b", timeVisible: true },
      });

      const series = chart.addSeries(AreaSeries, {
        lineColor: "#818cf8",
        topColor: "rgba(99, 102, 241, 0.35)",
        bottomColor: "rgba(99, 102, 241, 0.02)",
        lineWidth: 2,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 5,
        crosshairMarkerBorderColor: "#818cf8",
        crosshairMarkerBackgroundColor: "#0f172a",
      });

      series.setData(bars.map((b) => ({ time: b.time as Time, value: b.close })));
      chartRef.current = chart;
      seriesRef.current = series;
      requestAnimationFrame(() => chart.timeScale().fitContent());

      // ── Volume pane ───────────────────────────────────────────────────────
      const volSeries = chart.addSeries(
        HistogramSeries,
        {
          priceFormat: { type: "volume" },
          priceScaleId: "vol",
        },
        1, // pane index 1
      );

      volSeries.setData(
        bars.map((b) => ({
          time: b.time as Time,
          value: b.volume,
          color:
            b.close >= b.open
              ? "rgba(34, 197, 94, 0.45)"
              : "rgba(239, 68, 68, 0.45)",
        }))
      );

      volumeSeriesRef.current = volSeries;

      // 75% price / 25% volume
      const panes = chart.panes();
      if (panes.length >= 2) {
        panes[0].setStretchFactor(3);
        panes[1].setStretchFactor(1);
      }

      // ── Event markers (news + SEC filings) ───────────────────────────────
      const allMarkers = events.map((ev) => ({
        time: ev.time as Time,
        position: "aboveBar" as const,
        color: SENTIMENT_COLOR[ev.sentiment],
        shape: ev.sentiment === "negative" ? ("arrowDown" as const) : ("arrowUp" as const),
        text: ev.title.length > 22 ? ev.title.slice(0, 22) + "…" : ev.title,
        size: 2,
      }));

      createSeriesMarkers(series, allMarkers);

      // Fire onViewChange on pan / zoom
      chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        onViewChangeRef.current?.();
      });

      // Fire onViewChange on container resize
      const ro = new ResizeObserver(() => onViewChangeRef.current?.());
      ro.observe(containerRef.current!);

      chart.subscribeCrosshairMove((param) => {
        if (!param.time) { onHoverRef.current(null); return; }
        const hit = events.find((ev) => ev.time === param.time);
        onHoverRef.current(hit ?? null);
      });

      return () => {
        ro.disconnect();
        chart.remove();
        seriesRef.current = null;
        volumeSeriesRef.current = null;
        maSeriesRef.current = [];
      };
    }, [bars, events]);

    // ── Moving average lines (separate effect — no chart flicker on toggle) ──
    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;

      // Remove previous MA series
      maSeriesRef.current.forEach((s) => {
        try { chart.removeSeries(s); } catch { /* chart may have been rebuilt */ }
      });
      maSeriesRef.current = [];

      if (!movingAverages?.length) return;

      movingAverages.forEach((ma) => {
        const line = chart.addSeries(LineSeries, {
          color: ma.color,
          lineWidth: 1,
          crosshairMarkerVisible: false,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(ma.data.map((d) => ({ time: d.time as Time, value: d.value })));
        maSeriesRef.current.push(line);
      });
    }, [movingAverages]);

    // Sync vertical highlight with active event
    useEffect(() => {
      const el = highlightRef.current;
      const chart = chartRef.current;
      if (!el || !chart) return;
      if (!activeEventTime) { el.style.display = "none"; return; }
      const x = chart.timeScale().timeToCoordinate(activeEventTime as Time);
      if (x === null) { el.style.display = "none"; return; }
      el.style.display = "block";
      el.style.left = `${x}px`;
    }, [activeEventTime]);

    return (
      <div className="relative w-full h-full">
        <div ref={containerRef} className="w-full h-full" />
        <div
          ref={highlightRef}
          className="absolute top-0 bottom-0 hidden pointer-events-none"
          style={{
            width: "2px",
            transform: "translateX(-50%)",
            background: "linear-gradient(to bottom, rgba(99,102,241,0.9), rgba(99,102,241,0.05))",
            boxShadow: "0 0 12px 2px rgba(99,102,241,0.45)",
            zIndex: 10,
          }}
        />
      </div>
    );
  }
);
StockChart.displayName = "StockChart";
export default StockChart;
