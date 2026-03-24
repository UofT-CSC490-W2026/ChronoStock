# Frontend Testing Setup

This directory contains the configuration and examples for frontend testing using Jest and React Testing Library.

## 📋 What's Configured

- **Jest**: Test runner and assertion library
- **React Testing Library**: Component testing utilities
- **jest-dom**: Additional matchers for DOM elements
- **@testing-library/user-event**: User interaction simulation

## 🧪 Available Commands

```bash
# Run all tests once
npm test

# Run tests in watch mode (re-run on file changes)
npm run test:watch

# Generate coverage report
npm run test:coverage
```

## 📁 Test File Structure

Tests should be placed in `__tests__` directories next to the code they test:

```
components/
├── ui/
│   ├── Navbar.tsx
│   └── __tests__/
│       └── Navbar.test.tsx
lib/
├── api.ts
└── __tests__/
    └── api.test.ts
```

Or at the root level in `__tests__/` for integration tests.

## 📝 Writing Tests

### Basic Component Test

```typescript
import { render, screen } from "@testing-library/react";
import MyComponent from "@/components/MyComponent";

describe("MyComponent", () => {
  it("should render without crashing", () => {
    render(<MyComponent />);
    expect(screen.getByText(/some text/i)).toBeInTheDocument();
  });
});
```

### Testing with User Interaction

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Button from "@/components/Button";

describe("Button", () => {
  it("should call onClick when clicked", async () => {
    const handleClick = jest.fn();
    const user = userEvent.setup();
    
    render(<Button onClick={handleClick}>Click me</Button>);
    await user.click(screen.getByRole("button"));
    
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
```

### Testing API Calls

```typescript
import { fetchStockData } from "@/lib/api";

describe("fetchStockData", () => {
  it("should fetch stock data", async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ticker: "AAPL", ... }),
    });

    const data = await fetchStockData("AAPL");
    expect(data.ticker).toBe("AAPL");
  });
});
```

## 🎯 Test Examples Included

1. **`lib/__tests__/api.test.ts`** - API function mocking examples
2. **`__tests__/auth.test.tsx`** - Context provider testing example
3. **`components/ui/__tests__/`** - Ready for component tests

## 🚀 Next Steps

1. Run tests to verify setup: `npm test`
2. Add more test files following the structure
3. Aim for >80% code coverage: `npm run test:coverage`
4. Update tests when features change

## 📚 Resources

- [React Testing Library Docs](https://testing-library.com/docs/react-testing-library/intro/)
- [Jest Docs](https://jestjs.io/docs/getting-started)
- [Testing Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)

## 🐛 Troubleshooting

**Tests not found:**
- Ensure files end with `.test.ts` or `.test.tsx`
- Check `jest.config.ts` for correct `testMatch` pattern

**Module not found errors:**
- Verify `@/` alias in `jest.config.ts`
- Check `tsconfig.json` has matching paths configuration

**Canvas/Chart related errors:**
- Mock chart libraries if needed in `jest.setup.ts`
