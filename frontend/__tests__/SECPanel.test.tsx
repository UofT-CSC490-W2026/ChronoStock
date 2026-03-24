import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SECPanel from "@/components/chart/SECPanel";
import { SECFiling } from "@/lib/api";

const filings: SECFiling[] = [
  { date: "2026-03-01", form: "8-K", items: ["2.02"], label: "Results of operations", url: "https://example.com/8k" },
  { date: "2026-03-02", form: "4", items: ["4"], label: "Insider buy", url: "https://example.com/4" },
];

describe("SECPanel", () => {
  it("renders nothing without filings", () => {
    const { container } = render(<SECPanel filings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("toggles sections and shows filing links", async () => {
    const user = userEvent.setup();
    render(<SECPanel filings={filings} />);

    await user.click(screen.getByRole("button", { name: /sec filing details/i }));
    await user.click(screen.getByRole("button", { name: /8-k corporate events/i }));
    expect(screen.getByRole("link", { name: /results of operations/i })).toHaveAttribute("href", filings[0].url);

    await user.click(screen.getByRole("button", { name: /4 insider transactions/i }));
    expect(screen.getByRole("link", { name: /insider buy/i })).toHaveAttribute("href", filings[1].url);
    expect(screen.queryByRole("link", { name: /results of operations/i })).not.toBeInTheDocument();
  });
});
