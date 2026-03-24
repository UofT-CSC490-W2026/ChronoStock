import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StockPage from "@/app/stock/[ticker]/page";
import {
  addToWatchlist,
  fetchEarnings,
  fetchNews,
  fetchSECFilings,
  fetchStockData,
  fetchWatchlist,
  removeFromWatchlist,
} from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const mockUseAuth = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "aapl" }),
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/components/ui/Navbar", () => ({
  __esModule: true,
  default: () => <div data-testid="navbar" />,
}));

jest.mock("@/components/chart/StockChart", () => {
  const React = require("react");
  return {
    __esModule: true,
    default: React.forwardRef(function MockStockChart(props: { onChartEventHover: (ev: unknown) => void; bars: unknown[] }, ref) {
      React.useImperativeHandle(ref, () => ({
        getXForTime: () => 100,
        getPositionForDate: () => ({ x: 100, y: 80 }),
      }));
      return (
        <button
          type="button"
          data-testid="stock-chart"
          onClick={() => props.onChartEventHover({ id: "e1", time: "2026-03-01", title: "Earnings beat", summary: "Summary", sentiment: "positive", source: "Reuters" })}
        >
          chart {props.bars.length}
        </button>
      );
    }),
  };
});

jest.mock("@/components/chart/EventPanel", () => ({
  __esModule: true,
  default: ({ events, onCardClick, onCardHover, expandedId }: { events: Array<{ id: string; title: string }>; onCardClick: (ev: { id: string; title: string }) => void; onCardHover: (ev: { id: string; time: string }, el: HTMLDivElement) => void; expandedId: string | null }) => (
    <div>
      {events.map((event) => (
        <div key={event.id}>
          <button onClick={() => onCardClick(event)}>{event.title}</button>
          <button onClick={() => onCardHover({ ...event, time: "2026-03-01" }, document.createElement("div"))}>hover {event.title}</button>
          {expandedId === event.id && <span>expanded {event.title}</span>}
        </div>
      ))}
    </div>
  ),
}));

jest.mock("@/components/chart/StockMetaBar", () => ({
  __esModule: true,
  default: () => <div data-testid="stock-meta" />,
}));

jest.mock("@/components/chart/NewsPanel", () => ({
  __esModule: true,
  default: ({ news }: { news: Array<{ title: string }> }) => <div>{news.map((n) => n.title).join(",") || "No recent news."}</div>,
}));

jest.mock("@/components/chart/SECPanel", () => ({
  __esModule: true,
  default: ({ filings }: { filings: Array<{ label: string }> }) => <div>{filings.map((f) => f.label).join(",")}</div>,
}));

jest.mock("lucide-react", () => ({
  FileChartColumn: (props: React.SVGProps<SVGSVGElement>) => <svg data-testid="file-chart" {...props} />,
  ExternalLink: (props: React.SVGProps<SVGSVGElement>) => <svg data-testid="external-link" {...props} />,
  ArrowLeftRight: (props: React.SVGProps<SVGSVGElement>) => <svg data-testid="arrow-left-right" {...props} />,
  Landmark: (props: React.SVGProps<SVGSVGElement>) => <svg data-testid="landmark" {...props} />,
  Newspaper: (props: React.SVGProps<SVGSVGElement>) => <svg data-testid="newspaper" {...props} />,
}));

jest.mock("@/lib/api", () => ({
  fetchStockData: jest.fn(),
  fetchWatchlist: jest.fn(),
  addToWatchlist: jest.fn(),
  removeFromWatchlist: jest.fn(),
  fetchNews: jest.fn(),
  fetchEarnings: jest.fn(),
  fetchSECFilings: jest.fn(),
}));

const stockData = {
  ticker: "AAPL",
  companyName: "Apple",
  bars: [
    { time: "2025-01-01", open: 90, high: 95, low: 85, close: 90, volume: 10 },
    { time: "2026-03-01", open: 90, high: 120, low: 88, close: 110, volume: 12 },
  ],
  events: [
    { id: "e1", time: "2026-03-01", title: "Earnings beat", summary: "Summary", sentiment: "positive" as const, source: "Reuters" },
  ],
  meta: { marketCap: 1_000_000_000_000 },
};

describe("StockPage", () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() { return 500; },
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() { return 300; },
    });
    HTMLElement.prototype.getBoundingClientRect = function () {
      return { x: 0, y: 0, width: 500, height: 300, top: 0, left: 0, bottom: 300, right: 500, toJSON() { return {}; } };
    };
  });

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    (fetchNews as jest.Mock).mockResolvedValue([{ id: "n1", title: "News item", time: "2026-03-01", publisher: "WSJ" }]);
    (fetchEarnings as jest.Mock).mockResolvedValue([{ date: "2026-03-01", epsEstimate: 1.2, reportedEps: 1.5, surprisePct: 10 }]);
    (fetchSECFilings as jest.Mock).mockResolvedValue([
      { date: "2026-03-01", form: "8-K", items: [], label: "8-K filing", url: "https://example.com/8k" },
      { date: "2026-03-01", form: "4", items: ["4"], label: "Insider filing", url: "https://example.com/form4" },
    ]);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders error state when stock fetch fails", async () => {
    mockUseAuth.mockReturnValue({ user: null, token: null });
    (fetchStockData as jest.Mock).mockRejectedValue(new Error("API down"));

    render(<StockPage />);

    expect(await screen.findByText("API down")).toBeInTheDocument();
  });

  it("renders guest stock page and sign-in CTA", async () => {
    mockUseAuth.mockReturnValue({ user: null, token: null });
    (fetchStockData as jest.Mock).mockResolvedValue(stockData);

    render(<StockPage />);

    expect(screen.getByText(/loading aapl/i)).toBeInTheDocument();
    expect(await screen.findByText("Apple")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in to save/i })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: /sign in for ai event analysis/i })).toHaveAttribute("href", "/login");
  });

  it("renders authenticated view, removes from watchlist, toggles MA/range, event expansion, and earnings card", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchStockData as jest.Mock).mockResolvedValue(stockData);
    (fetchWatchlist as jest.Mock).mockResolvedValue([{ ticker: "AAPL", added_at: "2026-01-01" }]);
    (removeFromWatchlist as jest.Mock).mockResolvedValue(undefined);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<StockPage />);

    expect(await screen.findByText("Apple")).toBeInTheDocument();
    expect(screen.getByTestId("stock-meta")).toBeInTheDocument();
    expect(screen.getByText(/positive/i)).toBeInTheDocument();
    expect(screen.getByText("News item")).toBeInTheDocument();
    expect(screen.getByText(/8-k filing,insider filing/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /saved/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /saved/i }));
    await waitFor(() => {
      expect(removeFromWatchlist).toHaveBeenCalledWith("aapl", "token");
    });

    await user.click(screen.getByRole("button", { name: /^sma 20$/i }));
    await user.click(screen.getByRole("button", { name: /1m/i }));
    await user.click(screen.getAllByRole("button", { name: "Earnings beat" })[0]);
    expect(screen.getByText("expanded Earnings beat")).toBeInTheDocument();

    await user.click(screen.getByText(/hover earnings beat/i));
    expect(document.querySelector("svg[style*='z-index: 50']")).not.toBeNull();

    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    const earningsToggle = document.querySelector("button.relative.inline-flex.h-5.w-9") as HTMLButtonElement;
    expect(earningsToggle).not.toBeNull();
    await user.click(earningsToggle);
    await user.click(screen.getAllByTitle(/earnings report/i)[0]);
    expect(screen.getByText(/^Earnings Beat$/)).toBeInTheDocument();
    expect(screen.getByText("+10.0%")).toBeInTheDocument();
  });

  it("adds to watchlist when the stock is not already saved", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchStockData as jest.Mock).mockResolvedValue(stockData);
    (fetchWatchlist as jest.Mock).mockResolvedValue([]);
    (addToWatchlist as jest.Mock).mockResolvedValue(undefined);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<StockPage />);

    await screen.findByText("Apple");
    await user.click(await screen.findByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(addToWatchlist).toHaveBeenCalledWith("aapl", "token");
    });
  });

  it("shows 8-K and Form 4 overlays and disables them on long ranges", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "user@example.com" }, token: "token" });
    (fetchStockData as jest.Mock).mockResolvedValue(stockData);
    (fetchWatchlist as jest.Mock).mockResolvedValue([]);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<StockPage />);

    await screen.findByText("Apple");

    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    const toggles = document.querySelectorAll("button.relative.inline-flex.h-5.w-9");
    expect(toggles.length).toBeGreaterThanOrEqual(3);

    await user.click(toggles[1] as HTMLButtonElement);
    await user.click(toggles[2] as HTMLButtonElement);

    expect(await screen.findByTitle("8-K Filing")).toBeInTheDocument();
    expect(await screen.findByTitle("Insider Transaction")).toBeInTheDocument();

    await user.click(screen.getByTitle("8-K Filing"));
    expect(screen.getByRole("link", { name: /8-k filing/i })).toHaveAttribute("href", "https://example.com/8k");

    await user.click(screen.getByTitle("Insider Transaction"));
    expect(screen.getByRole("link", { name: /insider filing/i })).toHaveAttribute("href", "https://example.com/form4");

    await user.click(screen.getByRole("button", { name: /5y/i }));
    expect(screen.getAllByText(/n\/a for 5y\+/i).length).toBe(2);

    const updatedToggles = document.querySelectorAll("button.relative.inline-flex.h-5.w-9");
    expect((updatedToggles[1] as HTMLButtonElement).disabled).toBe(true);
    expect((updatedToggles[2] as HTMLButtonElement).disabled).toBe(true);
  });
});
