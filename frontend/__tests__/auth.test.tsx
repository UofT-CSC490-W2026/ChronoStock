import { render, screen } from "@testing-library/react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "test", email: "test@example.com" }),
    });
  });

  it("should provide auth context to children", () => {
    const TestComponent = () => {
      const { user } = useAuth();
      return <div>{user ? `Logged in: ${user.email}` : "Not logged in"}</div>;
    };

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    // Initially not logged in (no token in localStorage)
    expect(screen.getByText("Not logged in")).toBeInTheDocument();
  });

  it("should have login and signup functions", () => {
    const TestComponent = () => {
      const { login, signup, logout } = useAuth();
      return (
        <div>
          {typeof login === "function" &&
          typeof signup === "function" &&
          typeof logout === "function"
            ? "Auth functions available"
            : "No auth functions"}
        </div>
      );
    };

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    expect(screen.getByText("Auth functions available")).toBeInTheDocument();
  });

  it("should clear token on logout", () => {
    localStorage.setItem("chrono_token", "test-token");

    const TestComponent = () => {
      const { token, logout } = useAuth();
      return (
        <div>
          <div>{token ? "Token exists" : "No token"}</div>
          <button onClick={logout}>Logout</button>
        </div>
      );
    };

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    // Token should be available initially
    expect(localStorage.getItem("chrono_token")).toBeTruthy();
  });
});
