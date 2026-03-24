import { createRef } from "react";
import { render } from "@testing-library/react";
import StockChart, { StockChartHandle } from "@/components/chart/StockChart";
import { __getCharts, __getMarkers, __resetCharts } from "lightweight-charts";

jest.mock("lightweight-charts");

describe("StockChart", () => {
  beforeEach(() => {
    __resetCharts();
  });

  it("creates price, volume, markers, and MA series", () => {
    const onHover = jest.fn();
    const onViewChange = jest.fn();
    const ref = createRef<StockChartHandle>();
    const { container } = render(
      <StockChart
        ref={ref}
        bars={[
          { time: "2026-03-01", open: 10, high: 12, low: 9, close: 11, volume: 100 },
          { time: "2026-03-02", open: 11, high: 14, low: 10, close: 13, volume: 150 },
        ]}
        events={[
          { id: "e1", time: "2026-03-02", title: "Headline", summary: "", sentiment: "negative", source: "Reuters" },
        ]}
        secFilings={[
          { date: "2026-03-02", form: "8-K", items: ["2.02"], label: "8-K", url: "https://example.com" },
        ]}
        activeEventTime="2026-03-02"
        onChartEventHover={onHover}
        onViewChange={onViewChange}
        movingAverages={[
          { period: 20, color: "#38bdf8", data: [{ time: "2026-03-02", value: 12 }] },
        ]}
      />
    );

    const chart = __getCharts()[0];
    expect(chart.addSeries).toHaveBeenCalledTimes(3);
    expect(__getMarkers()).toHaveLength(1);

    chart.__visibleRangeHandler?.();
    expect(onViewChange).toHaveBeenCalled();

    chart.__crosshairHandler?.({ time: "2026-03-02" });
    expect(onHover).toHaveBeenCalledWith(expect.objectContaining({ id: "e1" }));

    expect(ref.current?.getXForTime("2026-03-02")).toBe(100);
    expect(ref.current?.getPositionForDate("2026-03-02", 13)).toEqual({ x: 100, y: 26 });

    const highlight = container.querySelector(".absolute.top-0.bottom-0.hidden.pointer-events-none") as HTMLDivElement;
    expect(highlight.style.display).toBe("block");
    expect(highlight.style.left).toBe("100px");
  });
});
