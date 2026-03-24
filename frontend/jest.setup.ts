import "@testing-library/jest-dom";

// Mock fetch globally for all tests
global.fetch = jest.fn();

// Reset fetch mock before each test
beforeEach(() => {
  (global.fetch as jest.Mock).mockClear();
});
