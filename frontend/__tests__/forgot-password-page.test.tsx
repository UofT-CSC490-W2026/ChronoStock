import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ForgotPasswordPage from "@/app/forgot-password/page";
import { requestPasswordReset } from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

jest.mock("@/lib/api", () => ({
  requestPasswordReset: jest.fn(),
}));

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("submits the email and shows the confirmation message", async () => {
    (requestPasswordReset as jest.Mock).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(requestPasswordReset).toHaveBeenCalledWith("user@example.com");
    });
    expect(await screen.findByText(/is registered, a reset link has been sent/i)).toBeInTheDocument();
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to sign in/i })).toHaveAttribute("href", "/login");
  });

  it("renders an error when the reset request fails", async () => {
    (requestPasswordReset as jest.Mock).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();

    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
  });
});
