import { createRef } from "react";
import { render } from "@testing-library/react";
import CompareChart, { CompareChartHandle } from "@/components/chart/CompareChart";
import { __getCharts, __getMarkers, __resetCharts } from "lightweight-charts";

jest.mock("lightweight-charts");

describe("CompareChart", () => {
  beforeEach(() => {
    __resetCharts();
  });

  it("builds a chart with one series per stock and exposes coordinates", () => {
    const ref = createRef<CompareChartHandle>();
    render(
      <CompareChart
        ref={ref}
        stocks={[
          {
            ticker: "AAPL",
            color: "#111",
            bars: [
              { time: "2026-03-01", open: 100, high: 101, low: 99, close: 100, volume: 10 },
              { time: "2026-03-02", open: 100, high: 111, low: 99, close: 110, volume: 12 },
            ],
            events: [{ id: "e1", time: "2026-03-02", title: "Upgrade", summary: "", sentiment: "positive", source: "WSJ" }],
          },
          {
            ticker: "MSFT",
            color: "#222",
            bars: [
              { time: "2026-03-01", open: 50, high: 55, low: 49, close: 50, volume: 7 },
              { time: "2026-03-02", open: 50, high: 52, low: 48, close: 51, volume: 8 },
            ],
            events: [{ id: "e2", time: "2026-03-02", title: "Launch", summary: "", sentiment: "neutral", source: "FT" }],
          },
        ]}
        visibleEventTickers={new Set(["AAPL"])}
      />
    );

    const chart = __getCharts()[0];
    expect(chart.addSeries).toHaveBeenCalledTimes(2);
    expect(__getMarkers()).toHaveLength(1);
    expect(ref.current?.getXForTime("2026-03-02")).toBe(100);
  });
});
