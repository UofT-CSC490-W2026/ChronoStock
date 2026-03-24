import { fetchStockData, searchTickers } from "@/lib/api";

describe("API Functions", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("searchTickers", () => {
    it("should return search results when API call succeeds", async () => {
      const mockResults = [
        { ticker: "AAPL", companyName: "Apple Inc." },
        { ticker: "GOOGL", companyName: "Alphabet Inc." },
      ];

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResults,
      });

      const results = await searchTickers("Apple");

      expect(results).toEqual(mockResults);
      expect(global.fetch).toHaveBeenCalled();
    });

    it("should throw error when API call fails", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(searchTickers("Apple")).rejects.toThrow();
    });
  });

  describe("fetchStockData", () => {
    it("should return stock data when API call succeeds", async () => {
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

      const result = await fetchStockData("AAPL");

      expect(result).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalled();
    });

    it("should throw error when ticker is not found", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(fetchStockData("INVALID")).rejects.toThrow();
    });
  });
});
