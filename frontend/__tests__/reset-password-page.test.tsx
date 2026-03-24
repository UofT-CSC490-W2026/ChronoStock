import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResetPasswordPage from "@/app/reset-password/page";
import { resetPassword } from "@/lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const push = jest.fn();
const getSearchParam = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: getSearchParam }),
}));

jest.mock("@/lib/api", () => ({
  resetPassword: jest.fn(),
}));

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getSearchParam.mockReturnValue("valid-token");
  });

  it("shows an error and disables submit when the token is missing", async () => {
    getSearchParam.mockReturnValue(null);

    render(<ResetPasswordPage />);

    expect(await screen.findByText("Missing or invalid reset token.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /set new password/i })).toBeDisabled();
  });

  it("validates mismatched passwords before submitting", async () => {
    const user = userEvent.setup();

    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "password456");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(resetPassword).not.toHaveBeenCalled();
  });

  it("submits the new password and redirects on success", async () => {
    (resetPassword as jest.Mock).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "password123");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    await waitFor(() => {
      expect(resetPassword).toHaveBeenCalledWith("valid-token", "password123");
    });
    expect(push).toHaveBeenCalledWith("/login?reset=1");
  });
});
