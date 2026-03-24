import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/login/page";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const push = jest.fn();
const login = jest.fn();
const getSearchParam = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: getSearchParam }),
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ login }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getSearchParam.mockReturnValue(null);
  });

  it("submits credentials and redirects on success", async () => {
    login.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith("user@example.com", "secret");
    });
    expect(push).toHaveBeenCalledWith("/");
  });

  it("renders auth errors", async () => {
    login.mockRejectedValue(new Error("Bad credentials"));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Bad credentials")).toBeInTheDocument();
  });
});
