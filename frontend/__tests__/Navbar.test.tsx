import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Navbar from "@/components/ui/Navbar";

jest.mock("next/image", () => ({
  __esModule: true,
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ""} />,
}));

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

jest.mock("@/components/ui/SearchBar", () => ({
  __esModule: true,
  default: () => <div data-testid="search-bar" />,
}));

describe("Navbar", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders auth links when logged out", () => {
    mockUseAuth.mockReturnValue({ user: null, logout: jest.fn() });

    render(<Navbar />);

    expect(screen.getByRole("link", { name: /home/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /compare/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /watchlist/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign up/i })).toBeInTheDocument();
  });

  it("renders user actions and truncates long emails", async () => {
    const logout = jest.fn();
    mockUseAuth.mockReturnValue({
      user: { email: "averylongemailaddress@example.com" },
      logout,
    });
    const user = userEvent.setup();

    render(<Navbar showSearch />);

    expect(screen.getByRole("link", { name: /watchlist/i })).toBeInTheDocument();
    expect(screen.getByTestId("search-bar")).toBeInTheDocument();
    expect(screen.getByText("averylongemailaddress...")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /sign out/i }));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
