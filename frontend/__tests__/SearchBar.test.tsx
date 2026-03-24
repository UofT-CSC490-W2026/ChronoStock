import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchBar from "@/components/ui/SearchBar";
import { searchTickers } from "@/lib/api";

const push = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

jest.mock("@/lib/api", () => ({
  searchTickers: jest.fn(),
}));

describe("SearchBar", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it("searches after debounce and navigates on enter", async () => {
    (searchTickers as jest.Mock).mockResolvedValue([
      { ticker: "AAPL", companyName: "Apple Inc." },
    ]);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<SearchBar />);
    await user.type(screen.getByPlaceholderText(/search ticker/i), "app");

    expect(searchTickers).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    expect(await screen.findByRole("button", { name: /aapl apple inc\./i })).toBeInTheDocument();

    await user.keyboard("{Enter}");
    expect(push).toHaveBeenCalledWith("/stock/AAPL");
  });

  it("clears results when query becomes empty", async () => {
    (searchTickers as jest.Mock).mockResolvedValue([
      { ticker: "MSFT", companyName: "Microsoft" },
    ]);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<SearchBar />);
    const input = screen.getByPlaceholderText(/search ticker/i);

    await user.type(input, "ms");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    expect(await screen.findByText("MSFT")).toBeInTheDocument();

    await user.clear(input);

    await waitFor(() => {
      expect(screen.queryByText("MSFT")).not.toBeInTheDocument();
    });
  });

  it("navigates when a result is clicked", async () => {
    (searchTickers as jest.Mock).mockResolvedValue([
      { ticker: "NVDA", companyName: "NVIDIA" },
    ]);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<SearchBar />);
    await user.type(screen.getByPlaceholderText(/search ticker/i), "nv");
    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    await user.click(await screen.findByRole("button", { name: /nvda nvidia/i }));
    expect(push).toHaveBeenCalledWith("/stock/NVDA");
  });
});
