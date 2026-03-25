import { render } from "@testing-library/react";
import MacroChart from "@/components/chart/MacroChart";
import { __getCharts, __resetCharts } from "lightweight-charts";

jest.mock("lightweight-charts");

describe("MacroChart", () => {
  beforeEach(() => {
    __resetCharts();
  });

  it("creates a line chart, formats prices, updates visible range, and cleans up", () => {
    const { rerender, unmount } = render(
      <MacroChart
        data={[
          { time: "2026-01-01", value: 2100.1234 },
          { time: "2026-01-02", value: 2200.5678 },
        ]}
        unit="$/oz"
        fromIndex={1}
      />
    );

    const chart = __getCharts()[0];
    expect(chart.addSeries).toHaveBeenCalledTimes(1);
    expect(chart.__series[0].setData).toHaveBeenCalledWith([
      { time: "2026-01-01", value: 2100.1234 },
      { time: "2026-01-02", value: 2200.5678 },
    ]);

    const chartOptions = (chart.addSeries.mock.calls[0] && chart.addSeries.mock.calls[0][1]) || null;
    expect(chartOptions).toMatchObject({
      color: "#818cf8",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });

    const timeScale = chart.timeScale();
    expect(timeScale.setVisibleLogicalRange).toHaveBeenCalledWith({ from: 1, to: 1 });

    const createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[0][1];
    const formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(1234.5)).toBe("1,234.50");

    rerender(
      <MacroChart
        data={[
          { time: "2026-01-01", value: 2100.1234 },
          { time: "2026-01-02", value: 2200.5678 },
        ]}
        unit="$/oz"
        fromIndex={0}
      />
    );

    const rerenderedChart = __getCharts()[1];
    expect(rerenderedChart.timeScale().setVisibleLogicalRange).toHaveBeenCalledWith({ from: 0, to: 1 });

    unmount();
    expect(chart.remove).toHaveBeenCalled();
    expect(rerenderedChart.remove).toHaveBeenCalled();
  });

  it("does not create a chart when no data is provided", () => {
    render(<MacroChart data={[]} unit="pts" />);
    expect(__getCharts()).toHaveLength(0);
  });

  it("formats K-units, pound prices, and default numeric values", () => {
    const { rerender } = render(
      <MacroChart
        data={[{ time: "2026-01-01", value: 1234.56 }]}
        unit="K jobs"
      />
    );

    let createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[0][1];
    let formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(1234.56)).toBe("1,235");

    rerender(
      <MacroChart
        data={[{ time: "2026-01-01", value: 4.56789 }]}
        unit="$/lb"
      />
    );

    createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[1][1];
    formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(4.56789)).toBe("4.5679");

    rerender(
      <MacroChart
        data={[{ time: "2026-01-01", value: 2.3456 }]}
        unit="%"
      />
    );

    createChartOptions = (require("lightweight-charts").createChart as jest.Mock).mock.calls[2][1];
    formatter = createChartOptions.localization.priceFormatter as (price: number) => string;
    expect(formatter(2.3456)).toBe("2.35");
  });
});
