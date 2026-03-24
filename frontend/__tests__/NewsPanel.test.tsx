import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewsPanel from "@/components/chart/NewsPanel";
import { StockNews } from "@/lib/api";

const news: StockNews[] = [
  {
    id: "n1",
    time: "2026-03-10",
    title: "Analysts raise guidance",
    publisher: "Bloomberg",
    summary: "Several analysts increased their price targets after the quarter.",
    url: "https://example.com/news",
    thumbnail: "https://example.com/thumb.jpg",
  },
];

describe("NewsPanel", () => {
  it("renders empty state", () => {
    render(<NewsPanel news={[]} />);
    expect(screen.getByText(/no recent news/i)).toBeInTheDocument();
  });

  it("expands and collapses an article", async () => {
    const user = userEvent.setup();
    render(<NewsPanel news={news} />);

    const card = screen.getByText(news[0].title).closest("div[class*='cursor-pointer']");
    expect(card).not.toBeNull();

    await user.click(card!);
    expect(screen.getByText(news[0].summary!)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /read full article/i })).toHaveAttribute("href", news[0].url);

    await user.click(card!);
    expect(screen.queryByText(news[0].summary!)).not.toBeInTheDocument();
  });
});
