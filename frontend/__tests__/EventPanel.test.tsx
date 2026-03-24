import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EventPanel from "@/components/chart/EventPanel";
import { NewsEvent } from "@/types";

const event: NewsEvent = {
  id: "ev-1",
  time: "2026-03-01",
  title: "Earnings beat expectations",
  summary: "Revenue and earnings both came in above consensus.",
  sentiment: "positive",
  source: "Reuters",
  url: "https://example.com/article",
};

describe("EventPanel", () => {
  it("renders empty state", () => {
    render(
      <EventPanel
        events={[]}
        activeEvent={null}
        onCardHover={jest.fn()}
        onCardClick={jest.fn()}
        expandedId={null}
      />
    );

    expect(screen.getByText(/no events for this period/i)).toBeInTheDocument();
  });

  it("fires hover and click callbacks", async () => {
    const onCardHover = jest.fn();
    const onCardClick = jest.fn();
    const user = userEvent.setup();

    render(
      <EventPanel
        events={[event]}
        activeEvent={event}
        onCardHover={onCardHover}
        onCardClick={onCardClick}
        expandedId={null}
      />
    );

    const card = screen.getByText(event.title).closest("div[class*='cursor-pointer']");
    expect(card).not.toBeNull();

    await user.hover(card!);
    expect(onCardHover).toHaveBeenCalledWith(event, expect.any(HTMLDivElement));

    await user.click(card!);
    expect(onCardClick).toHaveBeenCalledWith(event);

    await user.unhover(card!);
    expect(onCardHover).toHaveBeenLastCalledWith(null, null);
  });

  it("shows expanded content for the selected event", () => {
    render(
      <EventPanel
        events={[event]}
        activeEvent={null}
        onCardHover={jest.fn()}
        onCardClick={jest.fn()}
        expandedId={event.id}
      />
    );

    expect(screen.getByText(event.summary)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /read full article/i })).toHaveAttribute("href", event.url);
    expect(screen.getByText(/collapse/i)).toBeInTheDocument();
  });
});
