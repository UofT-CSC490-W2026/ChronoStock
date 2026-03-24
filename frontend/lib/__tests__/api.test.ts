import {
  addToWatchlist,
  fetchEarnings,
  fetchNews,
  fetchPrices,
  fetchSECFilings,
  fetchStockData,
  fetchTrending,
  fetchWatchlist,
  requestPasswordReset,
  resetPassword,
  removeFromWatchlist,
  searchTickers,
} from "@/lib/api";

describe("API Functions", () => {
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  });

  afterAll(() => {
    if (originalMockAuth === undefined) {
      delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    } else {
      process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
    }
  });

  describe("searchTickers", () => {
    it("returns search results when API call succeeds", async () => {
      const mockResults = [
        { ticker: "AAPL", companyName: "Apple Inc." },
        { ticker: "GOOGL", companyName: "Alphabet Inc." },
      ];

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResults,
      });

      await expect(searchTickers("Apple")).resolves.toEqual(mockResults);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/search?q=Apple");
    });

    it("throws error when API call fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(searchTickers("Apple")).rejects.toThrow("API error 500");
    });
  });

  describe("fetchStockData", () => {
    it("returns stock data when API call succeeds", async () => {
      const mockData = {
        ticker: "AAPL",
        companyName: "Apple Inc.",
        bars: [
          {
            time: "2025-01-01",
            open: 150,
            high: 151,
            low: 149,
            close: 150.5,
            volume: 1000000,
          },
        ],
        events: [],
        meta: {},
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      });

      await expect(fetchStockData("AAPL")).resolves.toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/stock/AAPL?range=ALL");
    });

    it("throws detailed error when API call fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
      });

      await expect(fetchStockData("INVALID")).rejects.toThrow("API error 404: Not Found");
    });
  });

  describe("fetchEarnings", () => {
    it("returns earnings when API call succeeds", async () => {
      const mockEarnings = [{ date: "2026-03-01", epsEstimate: 1.2 }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockEarnings,
      });

      await expect(fetchEarnings("AAPL")).resolves.toEqual(mockEarnings);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/earnings/AAPL");
    });

    it("returns empty array when API response is not ok", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
      await expect(fetchEarnings("AAPL")).resolves.toEqual([]);
    });

    it("returns empty array when fetch throws", async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));
      await expect(fetchEarnings("AAPL")).resolves.toEqual([]);
    });
  });

  describe("fetchNews", () => {
    it("returns news when API call succeeds", async () => {
      const mockNews = [{ id: "n1", title: "Headline", time: "2026-03-01", publisher: "WSJ" }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockNews,
      });

      await expect(fetchNews("AAPL")).resolves.toEqual(mockNews);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/news/AAPL");
    });

    it("returns empty array when news response is not ok", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
      await expect(fetchNews("AAPL")).resolves.toEqual([]);
    });

    it("returns empty array when news fetch throws", async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));
      await expect(fetchNews("AAPL")).resolves.toEqual([]);
    });
  });

  describe("fetchPrices", () => {
    it("returns empty array when no tickers are provided", async () => {
      await expect(fetchPrices([])).resolves.toEqual([]);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("returns prices when API call succeeds", async () => {
      const mockPrices = [{ ticker: "AAPL", companyName: "Apple", price: 210 }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockPrices,
      });

      await expect(fetchPrices(["AAPL", "MSFT"])).resolves.toEqual(mockPrices);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/prices?tickers=AAPL,MSFT");
    });

    it("returns empty array when prices response is not ok", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
      await expect(fetchPrices(["AAPL"])).resolves.toEqual([]);
    });

    it("returns empty array when prices fetch throws", async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));
      await expect(fetchPrices(["AAPL"])).resolves.toEqual([]);
    });
  });

  describe("fetchTrending", () => {
    it("returns trending items when API call succeeds", async () => {
      const mockTrending = [{ ticker: "AAPL", companyName: "Apple", changePct: 1.2 }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTrending,
      });

      await expect(fetchTrending()).resolves.toEqual(mockTrending);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/trending");
    });

    it("returns empty array when trending response is not ok", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
      await expect(fetchTrending()).resolves.toEqual([]);
    });

    it("returns empty array when trending fetch throws", async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));
      await expect(fetchTrending()).resolves.toEqual([]);
    });
  });

  describe("fetchSECFilings", () => {
    it("returns SEC filings when API call succeeds", async () => {
      const mockFilings = [{ date: "2026-03-01", form: "8-K", items: [], label: "8-K", url: "https://example.com" }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFilings,
      });

      await expect(fetchSECFilings("AAPL")).resolves.toEqual(mockFilings);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/sec/AAPL");
    });

    it("returns empty array when SEC response is not ok", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
      await expect(fetchSECFilings("AAPL")).resolves.toEqual([]);
    });

    it("returns empty array when SEC fetch throws", async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));
      await expect(fetchSECFilings("AAPL")).resolves.toEqual([]);
    });
  });

  describe("watchlist requests", () => {
    it("fetches the watchlist with the bearer token", async () => {
      const mockWatchlist = [{ ticker: "AAPL", added_at: "2026-03-01" }];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockWatchlist,
      });

      await expect(fetchWatchlist("token-123")).resolves.toEqual(mockWatchlist);
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist", {
        headers: { Authorization: "Bearer token-123" },
      });
    });

    it("throws when fetching the watchlist fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(fetchWatchlist("token-123")).rejects.toThrow("API error 401");
    });

    it("adds a stock to the watchlist", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true });

      await expect(addToWatchlist("AAPL", "token-123")).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist/AAPL", {
        method: "POST",
        headers: { Authorization: "Bearer token-123" },
      });
    });

    it("throws when addToWatchlist fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(addToWatchlist("AAPL", "token-123")).rejects.toThrow("API error 500");
    });

    it("removes a stock from the watchlist", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true });

      await expect(removeFromWatchlist("AAPL", "token-123")).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/api/watchlist/AAPL", {
        method: "DELETE",
        headers: { Authorization: "Bearer token-123" },
      });
    });

    it("throws when removeFromWatchlist fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(removeFromWatchlist("AAPL", "token-123")).rejects.toThrow("API error 500");
    });

    it("uses mock watchlist storage when mock auth is enabled", async () => {
      process.env.NEXT_PUBLIC_MOCK_AUTH = "true";

      await expect(fetchWatchlist("token-123")).resolves.toEqual([]);
      await expect(addToWatchlist("aapl", "token-123")).resolves.toBeUndefined();
      await expect(addToWatchlist("AAPL", "token-123")).resolves.toBeUndefined();
      await expect(fetchWatchlist("token-123")).resolves.toEqual([
        expect.objectContaining({ ticker: "AAPL" }),
      ]);

      await expect(removeFromWatchlist("aapl", "token-123")).resolves.toBeUndefined();
      await expect(fetchWatchlist("token-123")).resolves.toEqual([]);
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  describe("password reset requests", () => {
    it("requests a password reset email", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true });

      await expect(requestPasswordReset("user@example.com")).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "user@example.com" }),
      });
    });

    it("throws when the password reset email request fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 500 });

      await expect(requestPasswordReset("user@example.com")).rejects.toThrow("API error 500");
    });

    it("resets the password successfully", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true });

      await expect(resetPassword("token-123", "new-password")).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: "token-123", new_password: "new-password" }),
      });
    });

    it("surfaces backend reset-password details", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: "Reset token expired" }),
      });

      await expect(resetPassword("token-123", "new-password")).rejects.toThrow("Reset token expired");
    });

    it("falls back to status code when reset-password detail cannot be parsed", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => {
          throw new Error("bad json");
        },
      });

      await expect(resetPassword("token-123", "new-password")).rejects.toThrow("API error 400");
    });
  });
});
