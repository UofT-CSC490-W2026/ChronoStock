import { render, screen, waitFor } from "@testing-library/react";
import Home from "@/app/page";
import { fetchTrending } from "@/lib/api";

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

jest.mock("@/components/ui/SearchBar", () => ({
  __esModule: true,
  default: () => <div data-testid="searchbar" />,
}));

jest.mock("@/lib/api", () => ({
  fetchTrending: jest.fn(),
}));

describe("Home page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows loading state before trending data arrives", () => {
    mockUseAuth.mockReturnValue({ user: null });
    (fetchTrending as jest.Mock).mockReturnValue(new Promise(() => {}));

    const { container } = render(<Home />);

    expect(screen.getByTestId("navbar")).toBeInTheDocument();
    expect(screen.getByTestId("searchbar")).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(6);
    expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders trending cards and hides sign-in banner for logged-in users", async () => {
    mockUseAuth.mockReturnValue({ user: { email: "test@example.com" } });
    (fetchTrending as jest.Mock).mockResolvedValue([
      { ticker: "AAPL", companyName: "Apple", price: 200, changePct: 2.5 },
      { ticker: "TSLA", companyName: "Tesla", price: 180, changePct: -1.25 },
    ]);

    render(<Home />);

    expect(await screen.findByRole("link", { name: /aapl/i })).toHaveAttribute("href", "/stock/AAPL");
    expect(screen.getByText("+2.50%")).toBeInTheDocument();
    expect(screen.getByText("-1.25%")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^sign in$/i })).not.toBeInTheDocument();
  });

  it("shows empty trending message", async () => {
    mockUseAuth.mockReturnValue({ user: null });
    (fetchTrending as jest.Mock).mockResolvedValue([]);

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText(/no trending data available/i)).toBeInTheDocument();
    });
  });
});
