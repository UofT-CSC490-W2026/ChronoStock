import RootLayout, { metadata } from "@/app/layout";

jest.mock("next/font/google", () => ({
  Geist: () => ({ variable: "geist-sans" }),
  Geist_Mono: () => ({ variable: "geist-mono" }),
}));

jest.mock("@/contexts/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <div data-testid="auth-provider">{children}</div>,
}));

describe("RootLayout", () => {
  it("exports metadata", () => {
    expect(metadata.title).toContain("ChronoStock");
  });

  it("wraps children with auth provider and font classes", () => {
    const tree = RootLayout({
      children: <div>Child content</div>,
    });

    expect(tree.props.className).toContain("geist-sans");
    expect(tree.props.className).toContain("geist-mono");
    expect(tree.props.children.props.className).toContain("min-h-full");
  });
});
