import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StockNewsPage from "@/app/stock/[ticker]/news/page";
import { fetchNews, fetchStockData } from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const getSearchParam = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "aapl" }),
  useSearchParams: () => ({ get: getSearchParam }),
}));

jest.mock("@/components/ui/Navbar", () => ({
  __esModule: true,
  default: () => <div data-testid="navbar" />,
}));

jest.mock("@/lib/api", () => ({
  fetchNews: jest.fn(),
  fetchStockData: jest.fn(),
}));

const newsItems = [
  {
    id: "n1",
    time: "2026-03-20",
    title: "Apple earnings surge",
    summary: "Quarterly results beat expectations.",
    publisher: "Reuters",
    url: "https://example.com/earnings",
    thumbnail: "https://example.com/image.jpg",
  },
  {
    id: "n2",
    time: "2026-02-01",
    title: "Apple supply chain update",
    summary: "Manufacturing outlook remains steady.",
    publisher: "Bloomberg",
    url: "https://example.com/supply",
  },
];

describe("StockNewsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getSearchParam.mockReturnValue("1M");
    (fetchNews as jest.Mock).mockResolvedValue(newsItems);
    (fetchStockData as jest.Mock).mockResolvedValue({ companyName: "Apple" });
  });

  it("loads stock news using the query range and filters articles by title", async () => {
    const user = userEvent.setup();

    render(<StockNewsPage />);

    expect(screen.getByText(/loading news/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchNews).toHaveBeenCalledWith("aapl");
      expect(fetchStockData).toHaveBeenCalledWith("aapl");
    });

    expect(await screen.findByText("Apple earnings surge")).toBeInTheDocument();
    expect(screen.queryByText("Apple supply chain update")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1M" })).toHaveClass("bg-indigo-600");

    await user.type(screen.getByPlaceholderText(/type keywords/i), "earnings");
    expect(screen.getByText("Apple earnings surge")).toBeInTheDocument();
    expect(screen.queryByText("Apple supply chain update")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to chart/i })).toHaveAttribute("href", "/stock/aapl");
  });

  it("shows the empty state when no article matches the timeline and title filter", async () => {
    getSearchParam.mockReturnValue("ALL");
    const user = userEvent.setup();

    render(<StockNewsPage />);

    await screen.findByText("Apple earnings surge");
    await user.type(screen.getByPlaceholderText(/type keywords/i), "merger");

    expect(await screen.findByText(/no news matches this timeline and title filter/i)).toBeInTheDocument();
  });
});
