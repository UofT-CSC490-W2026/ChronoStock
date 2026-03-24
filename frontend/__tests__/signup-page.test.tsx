import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignupPage from "@/app/signup/page";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const push = jest.fn();
const signup = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ signup }),
}));

describe("SignupPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("submits credentials and redirects on success", async () => {
    signup.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<SignupPage />);

    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(signup).toHaveBeenCalledWith("new@example.com", "secret");
    });
    expect(push).toHaveBeenCalledWith("/");
  });

  it("renders signup errors", async () => {
    signup.mockRejectedValue(new Error("Email already exists"));
    const user = userEvent.setup();
    render(<SignupPage />);

    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Email already exists")).toBeInTheDocument();
  });
});
