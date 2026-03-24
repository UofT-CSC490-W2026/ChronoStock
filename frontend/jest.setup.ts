import "@testing-library/jest-dom";

// Mock fetch globally for all tests
global.fetch = jest.fn();

global.requestAnimationFrame = (cb: FrameRequestCallback): number => {
  cb(0);
  return 0;
};

global.cancelAnimationFrame = (_id: number): void => {};

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

global.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;

// Reset fetch mock before each test
beforeEach(() => {
  (global.fetch as jest.Mock).mockClear();
});
