import { render, screen } from "@testing-library/react";
import StockMetaBar from "@/components/chart/StockMetaBar";

describe("StockMetaBar", () => {
  it("formats major values and optional fields", () => {
    render(
      <StockMetaBar
        meta={{
          marketCap: 1_500_000_000_000,
          revenue: 85_000_000_000,
          eps: 6.12,
          peRatio: 25.3,
          forwardPE: 21.8,
          beta: 1.24,
          volume: 3_450_000,
          previousClose: 201.12,
          dayLow: 199.1,
          dayHigh: 205.45,
          weekLow52: 120,
          weekHigh52: 260,
          dividendRate: 0.96,
          dividendYield: 0.0048,
          earningsDate: "2026-04-28",
          analystRating: "Buy",
          priceTarget: 240,
        }}
      />
    );

    expect(screen.getByText("$1.50T")).toBeInTheDocument();
    expect(screen.getByText("$85.00B")).toBeInTheDocument();
    expect(screen.getByText("$6.12")).toBeInTheDocument();
    expect(screen.getByText("25.30")).toBeInTheDocument();
    expect(screen.getByText("3.45M")).toBeInTheDocument();
    expect(screen.getByText(/\$199\.10.*\$205\.45/)).toBeInTheDocument();
    expect(screen.getByText(/\$120\.00.*\$260\.00/)).toBeInTheDocument();
    expect(screen.getByText("$0.96 (0.48%)")).toBeInTheDocument();
    expect(screen.getByText("2026-04-28")).toBeInTheDocument();
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("$240.00")).toBeInTheDocument();
  });

  it("falls back to dashes when values are missing", () => {
    render(<StockMetaBar meta={{}} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(1);
  });
});
