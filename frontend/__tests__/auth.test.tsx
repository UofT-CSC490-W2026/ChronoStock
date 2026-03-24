import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

function TestHarness() {
  const { user, token, login, signup, logout } = useAuth();

  return (
    <div>
      <div>{user ? `Logged in: ${user.email}` : "Not logged in"}</div>
      <div>{token ? `Token: ${token}` : "No token"}</div>
      <button onClick={() => login("user@example.com", "secret")}>Run login</button>
      <button onClick={() => signup("new@example.com", "secret")}>Run signup</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  });

  afterAll(() => {
    if (originalMockAuth === undefined) {
      delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    } else {
      process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
    }
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

  it("restores token on mount and clears it on logout", async () => {
    localStorage.setItem("chrono_token", "test-token");
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "test", email: "test@example.com" }),
    });
    const user = userEvent.setup();

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

    await waitFor(() => {
      expect(screen.getByText("Token exists")).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /logout/i }));
    });

    expect(localStorage.getItem("chrono_token")).toBeNull();
    expect(screen.getByText("No token")).toBeInTheDocument();
  });

  it("removes invalid stored token when auth check fails", async () => {
    localStorage.setItem("chrono_token", "bad-token");
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({}),
    });

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(localStorage.getItem("chrono_token")).toBeNull();
    });
    expect(screen.getByText("Not logged in")).toBeInTheDocument();
  });

  it("logs in successfully and stores the token", async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: "login-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "user-1", email: "user@example.com" }),
      });
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /run login/i }));

    await waitFor(() => {
      expect(screen.getByText("Logged in: user@example.com")).toBeInTheDocument();
    });
    expect(screen.getByText("Token: login-token")).toBeInTheDocument();
    expect(localStorage.getItem("chrono_token")).toBe("login-token");
    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/auth/login",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/auth/me",
      expect.objectContaining({
        headers: { Authorization: "Bearer login-token" },
      })
    );
  });

  it("surfaces backend login errors and keeps user logged out", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: "Invalid credentials" }),
    });
    const user = userEvent.setup();

    const onError = jest.fn();
    function ErrorHarness() {
      const { login } = useAuth();
      return (
        <button
          onClick={async () => {
            try {
              await login("user@example.com", "secret");
            } catch (error) {
              onError(error);
            }
          }}
        >
          Trigger login error
        </button>
      );
    }

    render(
      <AuthProvider>
        <ErrorHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /trigger login error/i }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: "Invalid credentials" }));
    });
    expect(localStorage.getItem("chrono_token")).toBeNull();
  });

  it("falls back to default login error when backend has no detail", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => {
        throw new Error("bad json");
      },
    });
    const user = userEvent.setup();

    const onError = jest.fn();
    function ErrorHarness() {
      const { login } = useAuth();
      return (
        <button
          onClick={async () => {
            try {
              await login("user@example.com", "secret");
            } catch (error) {
              onError(error);
            }
          }}
        >
          Trigger fallback login error
        </button>
      );
    }

    render(
      <AuthProvider>
        <ErrorHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /trigger fallback login error/i }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: "Login failed" }));
    });
  });

  it("signs up successfully and stores the token", async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: "signup-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "user-2", email: "new@example.com" }),
      });
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /run signup/i }));

    await waitFor(() => {
      expect(screen.getByText("Logged in: new@example.com")).toBeInTheDocument();
    });
    expect(screen.getByText("Token: signup-token")).toBeInTheDocument();
    expect(localStorage.getItem("chrono_token")).toBe("signup-token");
    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/auth/signup",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/auth/me",
      expect.objectContaining({
        headers: { Authorization: "Bearer signup-token" },
      })
    );
  });

  it("surfaces signup errors and fallback message", async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: "Email exists" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => {
          throw new Error("bad json");
        },
      });
    const user = userEvent.setup();

    const onError = jest.fn();
    function ErrorHarness() {
      const { signup } = useAuth();
      return (
        <>
          <button
            onClick={async () => {
              try {
                await signup("new@example.com", "secret");
              } catch (error) {
                onError(error);
              }
            }}
          >
            Trigger signup error
          </button>
          <button
            onClick={async () => {
              try {
                await signup("new@example.com", "secret");
              } catch (error) {
                onError(error);
              }
            }}
          >
            Trigger fallback signup error
          </button>
        </>
      );
    }

    render(
      <AuthProvider>
        <ErrorHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /trigger signup error/i }));
    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: "Email exists" }));
    });

    await user.click(screen.getByRole("button", { name: /trigger fallback signup error/i }));
    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: "Signup failed" }));
    });
  });

  it("restores mock auth session from localStorage", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    localStorage.setItem("chrono_token", "mock-token");
    localStorage.setItem("chrono_user", JSON.stringify({ id: "mock-id", email: "mock@example.com" }));

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Logged in: mock@example.com")).toBeInTheDocument();
    });
    expect(screen.getByText("Token: mock-token")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("clears invalid mock auth session data", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    localStorage.setItem("chrono_token", "mock-token");
    localStorage.setItem("chrono_user", "{not-json");

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(localStorage.getItem("chrono_token")).toBeNull();
    });
    expect(localStorage.getItem("chrono_user")).toBeNull();
  });

  it("uses mock auth for login and signup when enabled", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <TestHarness />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /run login/i }));
    await waitFor(() => {
      expect(screen.getByText("Logged in: user@example.com")).toBeInTheDocument();
    });
    expect(localStorage.getItem("chrono_token")).toMatch(/^mock-token-/);
    expect(localStorage.getItem("chrono_user")).toContain("user@example.com");

    await user.click(screen.getByRole("button", { name: /logout/i }));
    await user.click(screen.getByRole("button", { name: /run signup/i }));

    await waitFor(() => {
      expect(screen.getByText("Logged in: new@example.com")).toBeInTheDocument();
    });
    expect(localStorage.getItem("chrono_token")).toMatch(/^mock-token-/);
    expect(localStorage.getItem("chrono_user")).toContain("new@example.com");
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
