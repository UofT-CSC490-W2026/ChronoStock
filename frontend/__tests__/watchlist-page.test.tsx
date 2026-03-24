import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WatchlistPage from "@/app/watchlist/page";
import { fetchPrices, fetchStockData, fetchWatchlist, removeFromWatchlist } from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const replace = jest.fn();
const router = { replace };
const mockUseAuth = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => router,
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/components/ui/Navbar", () => ({
  __esModule: true,
  default: () => <div data-testid="navbar" />,
}));

jest.mock("@/lib/api", () => ({
  fetchWatchlist: jest.fn(),
  fetchPrices: jest.fn(),
  fetchStockData: jest.fn(),
  removeFromWatchlist: jest.fn(),
}));

describe("WatchlistPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("redirects guests to login", async () => {
    mockUseAuth.mockReturnValue({ user: null, token: null });
    render(<WatchlistPage />);

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login");
    });
  });

  it("shows empty state when watchlist is empty", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockResolvedValue([]);
    (fetchPrices as jest.Mock).mockResolvedValue([]);

    render(<WatchlistPage />);

    expect(screen.getByText(/loading watchlist/i)).toBeInTheDocument();
    expect(await screen.findByText(/no stocks saved yet/i)).toBeInTheDocument();
  });

  it("renders rows and removes items", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "AAPL", added_at: "2026-01-01" }]);
    (fetchPrices as jest.Mock).mockResolvedValue([{ ticker: "AAPL", companyName: "Apple", price: 210, changePct: 1.5 }]);
    (fetchStockData as jest.Mock).mockResolvedValue({
      ticker: "AAPL",
      companyName: "Apple",
      bars: [
        { time: "2026-01-01", open: 100, high: 100, low: 100, close: 100, volume: 10 },
        { time: "2026-03-01", open: 100, high: 115, low: 90, close: 110, volume: 15 },
      ],
      events: [],
      meta: { marketCap: 1_000_000_000_000, peRatio: 20, weekLow52: 90, weekHigh52: 150 },
    });
    (removeFromWatchlist as jest.Mock).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<WatchlistPage />);

    expect(await screen.findByRole("link", { name: "AAPL" })).toHaveAttribute("href", "/stock/AAPL");
    expect(screen.getByText("+1.50%")).toBeInTheDocument();
    expect(screen.getByText("$1.00T")).toBeInTheDocument();
    expect(screen.getByText("20.0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove aapl/i }));

    await waitFor(() => {
      expect(removeFromWatchlist).toHaveBeenCalledWith("AAPL", "token");
    });
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "AAPL" })).not.toBeInTheDocument();
    });
  });

  it("falls back to empty state when fetching watchlist fails", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockRejectedValue(new Error("boom"));
    (fetchPrices as jest.Mock).mockResolvedValue([]);

    render(<WatchlistPage />);

    expect(await screen.findByText(/no stocks saved yet/i)).toBeInTheDocument();
  });

  it("renders fallback values when stock data is missing", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "MSFT", added_at: "2026-01-01" }]);
    (fetchPrices as jest.Mock).mockResolvedValue([]);
    (fetchStockData as jest.Mock).mockRejectedValue(new Error("missing"));

    const { container } = render(<WatchlistPage />);

    expect(await screen.findByRole("link", { name: "MSFT" })).toHaveAttribute("href", "/stock/MSFT");
    expect(screen.getAllByText("—").length).toBeGreaterThan(1);
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("renders sparkline and range bar without marker when range cannot be computed", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "NVDA", added_at: "2026-01-01" }]);
    (fetchPrices as jest.Mock).mockResolvedValue([{ ticker: "NVDA", companyName: "NVIDIA" }]);
    (fetchStockData as jest.Mock).mockResolvedValue({
      ticker: "NVDA",
      companyName: "NVIDIA",
      bars: [
        { time: "2026-01-01", open: 20, high: 22, low: 19, close: 20, volume: 10 },
        { time: "2026-03-01", open: 20, high: 24, low: 18, close: 23, volume: 15 },
      ],
      events: [],
      meta: { marketCap: 950_000, peRatio: 12.5, weekLow52: 50, weekHigh52: 50 },
    });

    const { container } = render(<WatchlistPage />);

    expect(await screen.findByRole("link", { name: "NVDA" })).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector(".bg-indigo-400")).toBeNull();
    expect(screen.getByText("$950,000")).toBeInTheDocument();
    expect(screen.getByText("12.5")).toBeInTheDocument();
  });

  it("shows row skeletons before per-stock requests resolve and falls back to bar-close price/company", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    let resolvePrices: (value: unknown) => void;
    let resolveStock: (value: unknown) => void;
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "TSLA", added_at: "2026-01-01" }]);
    (fetchPrices as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePrices = resolve;
        })
    );
    (fetchStockData as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStock = resolve;
        })
    );

    const { container } = render(<WatchlistPage />);

    await waitFor(() => {
      expect(fetchPrices).toHaveBeenCalledWith(["TSLA"]);
    });
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);

    resolvePrices!([]);
    await waitFor(() => {
      expect(fetchStockData).toHaveBeenCalledWith("TSLA");
    });
    resolveStock!({
      ticker: "TSLA",
      companyName: "Tesla",
      bars: [
        { time: "2026-01-01", open: 300, high: 310, low: 295, close: 300, volume: 100 },
        { time: "2026-03-01", open: 300, high: 340, low: 290, close: 325, volume: 110 },
      ],
      events: [],
      meta: { weekLow52: 200, weekHigh52: 400 },
    });

    expect(await screen.findByRole("link", { name: "TSLA" })).toHaveAttribute("href", "/stock/TSLA");
    expect(screen.getByText("Tesla")).toBeInTheDocument();
    expect(screen.getByText("$325.00")).toBeInTheDocument();
    expect(screen.getByText("$200")).toBeInTheDocument();
    expect(screen.getByText("$400")).toBeInTheDocument();
  });

  it("keeps the row when remove fails", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "AAPL", added_at: "2026-01-01" }]);
    (fetchPrices as jest.Mock).mockResolvedValue([{ ticker: "AAPL", companyName: "Apple", price: 210, changePct: -1.5 }]);
    (fetchStockData as jest.Mock).mockResolvedValue({
      ticker: "AAPL",
      companyName: "Apple",
      bars: [
        { time: "2026-01-01", open: 100, high: 110, low: 90, close: 100, volume: 10 },
        { time: "2026-03-01", open: 100, high: 105, low: 80, close: 95, volume: 15 },
      ],
      events: [],
      meta: { marketCap: 1_000_000_000, peRatio: 20, weekLow52: 80, weekHigh52: 150 },
    });
    (removeFromWatchlist as jest.Mock).mockRejectedValue(new Error("cannot remove"));
    const user = userEvent.setup();

    render(<WatchlistPage />);

    expect(await screen.findByRole("link", { name: "AAPL" })).toBeInTheDocument();
    expect(screen.getByText("-1.50%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove aapl/i }));

    await waitFor(() => {
      expect(removeFromWatchlist).toHaveBeenCalledWith("AAPL", "token");
    });
    expect(screen.getByRole("link", { name: "AAPL" })).toBeInTheDocument();
  });
});
