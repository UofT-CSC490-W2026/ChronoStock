import { createRef } from "react";
import { render } from "@testing-library/react";
import CompareChart, { CompareChartHandle } from "@/components/chart/CompareChart";
import { __getCharts, __getMarkers, __resetCharts } from "lightweight-charts";

jest.mock("lightweight-charts");

describe("CompareChart", () => {
  beforeEach(() => {
    __resetCharts();
  });

  it("builds a normalized chart with one series per stock and exposes coordinates", () => {
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
        normalized
      />
    );

    const chart = __getCharts()[0];
    expect(chart.addSeries).toHaveBeenCalledTimes(2);
    expect(chart.__series[0].setData).toHaveBeenCalledWith([
      { time: "2026-03-01", value: 0 },
      { time: "2026-03-02", value: 10 },
    ]);
    expect(__getMarkers()).toHaveLength(1);
    expect(ref.current?.getXForTime("2026-03-02")).toBe(100);

    const createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[0][1];
    const formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(1.234)).toBe("+1.23%");
    expect(formatter(-1.234)).toBe("-1.23%");
  });

  it("supports raw mode, subscribes view changes, and builds marker styles for all sentiments", () => {
    const onViewChange = jest.fn();
    render(
      <CompareChart
        stocks={[
          {
            ticker: "TSLA",
            color: "#333",
            bars: [
              { time: "2026-03-01", open: 200, high: 205, low: 198, close: 201, volume: 10 },
              { time: "2026-03-02", open: 201, high: 210, low: 199, close: 208, volume: 11 },
            ],
            events: [
              { id: "e1", time: "2026-03-01", title: "Short negative headline", summary: "", sentiment: "negative", source: "WSJ" },
              { id: "e2", time: "2026-03-02", title: "A very long event title that should be truncated", summary: "", sentiment: "neutral", source: "FT" },
            ],
          },
        ]}
        visibleEventTickers={new Set(["TSLA"])}
        normalized={false}
        onViewChange={onViewChange}
      />
    );

    const chart = __getCharts()[0];
    expect(chart.__series[0].setData).toHaveBeenCalledWith([
      { time: "2026-03-01", value: 201 },
      { time: "2026-03-02", value: 208 },
    ]);

    const createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[0][1];
    const formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(12.3)).toBe("$12.30");

    const timeScale = chart.timeScale();
    expect(timeScale.subscribeVisibleLogicalRangeChange).toHaveBeenCalledWith(onViewChange);
    expect(timeScale.fitContent).toHaveBeenCalled();
    expect(onViewChange).toHaveBeenCalledTimes(1);

    const markers = __getMarkers()[0] as { markers: Array<{ color: string; shape: string; text: string }> };
    expect(markers.markers).toHaveLength(2);
    expect(markers.markers[0]).toMatchObject({
      color: "#ef4444",
      shape: "arrowDown",
      text: "[TSLA] Short negative hea…",
    });
    expect(markers.markers[1]).toMatchObject({
      color: "#f59e0b",
      shape: "arrowUp",
      text: "[TSLA] A very long event …",
    });
  });

  it("handles empty bar series and skips markers for hidden tickers", () => {
    render(
      <CompareChart
        stocks={[
          {
            ticker: "NFLX",
            color: "#444",
            bars: [],
            events: [{ id: "e1", time: "2026-03-02", title: "No marker", summary: "", sentiment: "positive", source: "WSJ" }],
          },
        ]}
        visibleEventTickers={new Set()}
        normalized
      />
    );

    const chart = __getCharts()[0];
    expect(chart.__series[0].setData).toHaveBeenCalledWith([]);
    expect(__getMarkers()).toHaveLength(0);
  });
});
