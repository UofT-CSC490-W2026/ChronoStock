type VisibleRangeHandler = () => void;
type CrosshairHandler = (param: { time?: string | null }) => void;

interface MockSeries {
  setData: jest.Mock<void, [unknown[]]>;
  priceToCoordinate: jest.Mock<number | null, [number]>;
}

interface MockChart {
  addSeries: jest.Mock<MockSeries, [unknown, unknown?, number?]>;
  removeSeries: jest.Mock<void, [MockSeries]>;
  remove: jest.Mock<void, []>;
  timeScale: jest.MockedFunction<() => {
    fitContent: jest.Mock<void, []>;
    timeToCoordinate: jest.Mock<number | null, [unknown]>;
    subscribeVisibleTimeRangeChange: jest.Mock<void, [VisibleRangeHandler]>;
  }>;
  subscribeCrosshairMove: jest.Mock<void, [CrosshairHandler]>;
  panes: jest.Mock<[{ setStretchFactor: jest.Mock<void, [number]> }, { setStretchFactor: jest.Mock<void, [number]> }], []>;
  __visibleRangeHandler?: VisibleRangeHandler;
  __crosshairHandler?: CrosshairHandler;
  __series: MockSeries[];
}

const charts: MockChart[] = [];
const markers: unknown[] = [];

function makeSeries(): MockSeries {
  return {
    setData: jest.fn(),
    priceToCoordinate: jest.fn((price: number) => price * 2),
  };
}

export const createChart = jest.fn(() => {
  const series: MockSeries[] = [];
  const timeScale = {
    fitContent: jest.fn(),
    timeToCoordinate: jest.fn((time: unknown) =>
      typeof time === "string" ? time.length * 10 : 100
    ),
    subscribeVisibleTimeRangeChange: jest.fn((handler: VisibleRangeHandler) => {
      chart.__visibleRangeHandler = handler;
    }),
  };

  const chart: MockChart = {
    addSeries: jest.fn((_type: unknown, _opts?: unknown, _pane?: number) => {
      const next = makeSeries();
      series.push(next);
      return next;
    }),
    removeSeries: jest.fn(),
    remove: jest.fn(),
    timeScale: jest.fn(() => timeScale),
    subscribeCrosshairMove: jest.fn((handler: CrosshairHandler) => {
      chart.__crosshairHandler = handler;
    }),
    panes: jest.fn(() => [
      { setStretchFactor: jest.fn() },
      { setStretchFactor: jest.fn() },
    ]),
    __series: series,
  };

  charts.push(chart);
  return chart;
});

export const createSeriesMarkers = jest.fn((series: MockSeries, nextMarkers: unknown[]) => {
  markers.push({ series, markers: nextMarkers });
});

export const AreaSeries = "AreaSeries";
export const HistogramSeries = "HistogramSeries";
export const LineSeries = "LineSeries";
export const ColorType = { Solid: "solid" };

export const __resetCharts = () => {
  charts.length = 0;
  markers.length = 0;
  createChart.mockClear();
  createSeriesMarkers.mockClear();
};

export const __getCharts = () => charts;
export const __getMarkers = () => markers;
