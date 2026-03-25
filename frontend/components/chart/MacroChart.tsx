"use client";

import { useEffect, useRef } from "react";
import { createChart, LineSeries, ColorType, Time, IChartApi } from "lightweight-charts";

interface MacroChartProps {
  data: { time: string; value: number }[];
  unit: string;
  /** Index of the first visible data point (0 = show all from start) */
  fromIndex?: number;
}

export default function MacroChart({ data, unit, fromIndex = 0 }: MacroChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#1e293b" },
      },
      crosshair: {
        vertLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
      },
      rightPriceScale: { borderColor: "#1e293b" },
      timeScale: { borderColor: "#1e293b", timeVisible: false },
      localization: {
        priceFormatter: (price: number) =>
          unit === "K jobs" || unit === "K"
            ? price.toLocaleString("en-US", { maximumFractionDigits: 0 })
            : unit === "$/oz" || unit === "$/bbl" || unit === "pts"
            ? price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : unit === "$/lb"
            ? price.toFixed(4)
            : price.toFixed(2),
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#818cf8",
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: "#818cf8",
      crosshairMarkerBackgroundColor: "#0f172a",
      priceLineVisible: false,
      lastValueVisible: true,
    });

    series.setData(data.map((d) => ({ time: d.time as Time, value: d.value })));
    chartRef.current = chart;

    // Initial visible range
    requestAnimationFrame(() => {
      chart.timeScale().setVisibleLogicalRange({
        from: fromIndex,
        to: data.length - 1,
      });
    });

    return () => {
      chartRef.current = null;
      chart.remove();
    };
    // Only recreate chart when data or unit changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, unit]);

  // Update visible range when fromIndex changes (without recreating chart)
  useEffect(() => {
    if (!chartRef.current || !data.length) return;
    chartRef.current.timeScale().setVisibleLogicalRange({
      from: fromIndex,
      to: data.length - 1,
    });
  }, [fromIndex, data.length]);

  return <div ref={containerRef} className="w-full h-full" />;
}
