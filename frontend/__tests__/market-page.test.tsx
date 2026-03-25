import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MarketPage from "@/app/market/page";
import { fetchIndicatorHistory, fetchMarketAnalysis, fetchMarketSummary } from "@/lib/api";

const mockUseAuth = jest.fn();
const mockMacroChart = jest.fn();

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/components/ui/Navbar", () => ({
  __esModule: true,
  default: () => <div data-testid="navbar" />,
}));

jest.mock("@/components/chart/MacroChart", () => ({
  __esModule: true,
  default: (props: { data: Array<{ time: string; value: number }>; unit: string; fromIndex?: number }) => {
    mockMacroChart(props);
    return <div data-testid="macro-chart">{`${props.unit}|${props.data.length}|${props.fromIndex ?? 0}`}</div>;
  },
}));

jest.mock("lucide-react", () => {
  const Icon = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />;
  return {
    TrendingUp: Icon,
    TrendingDown: Icon,
    Minus: Icon,
    Sparkles: Icon,
    Clock: Icon,
    BookOpen: Icon,
    Zap: Icon,
    Eye: Icon,
    LineChart: Icon,
    X: Icon,
  };
});

jest.mock("@/lib/api", () => ({
  fetchMarketSummary: jest.fn(),
  fetchMarketAnalysis: jest.fn(),
  fetchIndicatorHistory: jest.fn(),
}));

const summary = {
  cachedAt: "2026-03-25T14:30:00Z",
  categories: [
    {
      name: "Growth",
      indicators: [
        {
          name: "Payrolls",
          value: 120,
          unit: "K jobs",
          change: 20,
          changePct: null,
          description: "Monthly payroll change",
          source: "BLS",
          asOf: "2026-03-01",
        },
        {
          name: "Gold",
          value: 2145.4,
          unit: "$/oz",
          change: 15.2,
          changePct: 0.71,
          description: "Gold spot price",
          source: "ICE",
          asOf: "2026-03-25",
        },
      ],
    },
  ],
};

const analysis = {
  generatedAt: "2026-03-25T12:00:00Z",
  regimeSentiment: "bullish",
  summary: "Liquidity and labor data still support risk assets.",
  regime: "Growth is slowing gradually, but financial conditions remain supportive.",
  narrative: "Rates eased.\nEquities extended gains.",
  keyDrivers: [
    { title: "Treasury yields", sentiment: "positive", explanation: "Lower real yields improved duration appetite." },
    { title: "Credit spreads", sentiment: "neutral", explanation: "Spreads remain contained." },
  ],
  historicalContext: "This resembles prior soft-landing periods.\nInflation is still the main constraint.",
  watchlist: [
    { indicator: "CPI", currentSignal: "Cooling month over month", whyItMatters: "Would validate easing inflation pressure." },
  ],
};

const history = {
  unit: "% YoY",
  data: [
    { time: "2025-01-01", value: 3.1 },
    { time: "2026-01-01", value: 2.8 },
  ],
};

describe("MarketPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders guest market overview, summary cards, and indicator history modal", async () => {
    let resolveHistory: ((value: typeof history) => void) | undefined;
    mockUseAuth.mockReturnValue({ user: null, token: null });
    (fetchMarketSummary as jest.Mock).mockResolvedValue(summary);
    (fetchIndicatorHistory as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveHistory = resolve as (value: typeof history) => void;
        })
    );
    const user = userEvent.setup();

    render(<MarketPage />);

    expect(screen.getByTestId("navbar")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /market overview/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");

    expect(await screen.findByText("Growth")).toBeInTheDocument();
    expect(screen.getByText("+120")).toBeInTheDocument();
    expect(screen.getByText("+20 K vs prev")).toBeInTheDocument();
    expect(screen.getByText("2,145.40")).toBeInTheDocument();
    expect(screen.getByText("+15.20 (+0.71%)")).toBeInTheDocument();

    await user.click(screen.getByText("Payrolls"));

    await waitFor(() => {
      expect(fetchIndicatorHistory).toHaveBeenCalledWith("Payrolls");
    });
    expect(screen.getByText(/loading historical data/i)).toBeInTheDocument();
    await act(async () => {
      resolveHistory?.(history);
    });
    expect(await screen.findByTestId("macro-chart")).toHaveTextContent("% YoY|2|0");
    expect(mockMacroChart).toHaveBeenLastCalledWith(
      expect.objectContaining({ unit: "% YoY", fromIndex: 0, data: history.data })
    );
    expect(screen.getByText(/2 data points \(5y\)/i)).toBeInTheDocument();

    const backdrop = document.querySelector(".fixed.inset-0.z-50") as HTMLDivElement;
    await user.click(backdrop);
    await waitFor(() => {
      expect(screen.queryByTestId("macro-chart")).not.toBeInTheDocument();
    });
  });

  it("renders AI analysis for authenticated users", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchMarketSummary as jest.Mock).mockResolvedValue(summary);
    (fetchMarketAnalysis as jest.Mock).mockResolvedValue(analysis);

    render(<MarketPage />);

    expect(await screen.findByText(/ai market analysis/i)).toBeInTheDocument();
    expect(fetchMarketAnalysis).toHaveBeenCalledWith("token");
    expect(await screen.findByText(/liquidity and labor data still support risk assets/i)).toBeInTheDocument();
    expect(screen.getByText(/what happened & why/i)).toBeInTheDocument();
    expect(screen.getByText("Rates eased.")).toBeInTheDocument();
    expect(screen.getByText("Equities extended gains.")).toBeInTheDocument();
    expect(screen.getByText(/key drivers/i)).toBeInTheDocument();
    expect(screen.getByText("Treasury yields")).toBeInTheDocument();
    expect(screen.getByText(/historical context/i)).toBeInTheDocument();
    expect(screen.getByText(/what to watch/i)).toBeInTheDocument();
    expect(screen.getByText("Cooling month over month")).toBeInTheDocument();
    expect(screen.getByText(/generated .*refreshes every 12 hours/i)).toBeInTheDocument();
  });

  it("shows market and analysis errors when fetches fail", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchMarketSummary as jest.Mock).mockRejectedValue(new Error("summary failed"));
    (fetchMarketAnalysis as jest.Mock).mockRejectedValue(new Error("analysis failed"));

    render(<MarketPage />);

    expect(await screen.findByText("summary failed")).toBeInTheDocument();
    expect(await screen.findByText("analysis failed")).toBeInTheDocument();
  });
});
