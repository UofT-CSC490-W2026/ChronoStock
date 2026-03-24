import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ComparePage from "@/app/compare/page";
import { fetchStockData, searchTickers } from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const mockUseAuth = jest.fn();

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/components/ui/Navbar", () => ({
  __esModule: true,
  default: () => <div data-testid="navbar" />,
}));

jest.mock("@/components/chart/CompareChart", () => {
  const React = require("react");
  return {
    __esModule: true,
    STOCK_COLORS: ["#1", "#2", "#3", "#4", "#5"],
    default: React.forwardRef(function MockCompareChart(
      {
        stocks,
        visibleEventTickers,
        normalized,
      }: {
        stocks: Array<{ ticker: string }>;
        visibleEventTickers: Set<string>;
        normalized: boolean;
      },
      ref
    ) {
      React.useImperativeHandle(ref, () => ({
        getXForTime: (time: string) => {
          if (time === "2026-01-02") return 10;
          if (time === "2026-01-12") return 40;
          return null;
        },
      }));
      return (
        <div data-testid="compare-chart">
          {normalized ? "normalized" : "raw"}|
          {stocks.map((s) => `${s.ticker}:${visibleEventTickers.has(s.ticker) ? "on" : "off"}`).join(",")}
        </div>
      );
    }),
  };
});

jest.mock("@/lib/api", () => ({
  fetchStockData: jest.fn(),
  searchTickers: jest.fn(),
}));

const buildBars = (base: number) =>
  Array.from({ length: 12 }, (_, i) => {
    const day = String(i + 1).padStart(2, "0");
    const close = base + i * 2;
    return { time: `2026-01-${day}`, open: close - 1, high: close + 1, low: close - 2, close, volume: 10 + i };
  });

const stockData = {
  ticker: "AAPL",
  companyName: "Apple",
  bars: buildBars(100),
  events: [
    { id: "e1", time: "2026-01-12", title: "Launch event", summary: "", sentiment: "positive", source: "Reuters" as const },
  ],
};

const msftStockData = {
  ticker: "MSFT",
  companyName: "Microsoft",
  bars: buildBars(200),
  events: [
    { id: "e2", time: "2026-01-12", title: "Cloud growth", summary: "", sentiment: "neutral", source: "Bloomberg" as const },
  ],
};

describe("ComparePage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it("shows guest sidebar CTA", () => {
    mockUseAuth.mockReturnValue({ user: null });
    render(<ComparePage />);

    expect(screen.getByText(/search and add stocks above to compare/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("adds a ticker, renders chart, and toggles events for signed-in users", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" } });
    (searchTickers as jest.Mock).mockResolvedValue([{ ticker: "AAPL", companyName: "Apple" }]);
    (fetchStockData as jest.Mock).mockResolvedValue(stockData);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<ComparePage />);

    await user.type(screen.getByPlaceholderText(/add ticker/i), "aa");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    await user.click(await screen.findByRole("button", { name: /aapl apple/i }));

    await waitFor(() => {
      expect(screen.getByTestId("compare-chart")).toHaveTextContent("AAPL:on");
    });
    expect(screen.getByText("Launch event")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1y/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /aapl.*1 events.*on/i }));
    await waitFor(() => {
      expect(screen.getByTestId("compare-chart")).toHaveTextContent("AAPL:off");
    });

    await user.click(screen.getByRole("button", { name: /remove aapl/i }));
    expect(screen.getByText(/search and add stocks above to compare/i)).toBeInTheDocument();
  });

  it("drops ticker if fetch fails", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" } });
    (searchTickers as jest.Mock).mockResolvedValue([{ ticker: "AAPL", companyName: "Apple" }]);
    (fetchStockData as jest.Mock).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<ComparePage />);

    await user.type(screen.getByPlaceholderText(/add ticker/i), "aa");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    await user.click(await screen.findByRole("button", { name: /aapl apple/i }));

    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });
  });

  it("supports keyboard selection, closing results, raw-price mode, and co-movement highlights", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" } });
    (searchTickers as jest.Mock)
      .mockResolvedValueOnce([{ ticker: "AAPL", companyName: "Apple" }])
      .mockResolvedValueOnce([{ ticker: "MSFT", companyName: "Microsoft" }])
      .mockResolvedValueOnce([{ ticker: "MSFT", companyName: "Microsoft" }]);
    (fetchStockData as jest.Mock)
      .mockResolvedValueOnce(stockData)
      .mockResolvedValueOnce(msftStockData);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<ComparePage />);

    const input = screen.getByPlaceholderText(/add ticker/i);
    await user.type(input, "aa");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    await user.click(await screen.findByRole("button", { name: /aapl apple/i }));

    await waitFor(() => {
      expect(screen.getByTestId("compare-chart")).toHaveTextContent("normalized|AAPL:on");
    });

    await user.clear(input);
    await user.type(input, "ms");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    expect(await screen.findByRole("button", { name: /msft microsoft/i })).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByRole("button", { name: /msft microsoft/i })).not.toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "ms");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByTestId("compare-chart")).toHaveTextContent("AAPL:on,MSFT:on");
    });

    await user.click(screen.getByTitle(/switch to raw price/i));
    expect(screen.getByTestId("compare-chart")).toHaveTextContent("raw|AAPL:on,MSFT:on");
    expect(screen.getByText(/chart shows raw price/i)).toBeInTheDocument();

    const coMovementToggle = screen.getByTitle(/highlight periods when all stocks moved together/i);
    expect(coMovementToggle).toBeEnabled();
    await user.click(coMovementToggle);
    expect(screen.getByText("0.80")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("slider"), { target: { value: "0.75" } });

    await waitFor(() => {
      expect(screen.getByText("0.75")).toBeInTheDocument();
    });
  });
});
