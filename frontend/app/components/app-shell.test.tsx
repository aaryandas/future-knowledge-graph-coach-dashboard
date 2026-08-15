import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/member",
}));

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
});

afterEach(cleanup);

describe("AppShell", () => {
  it("hides and restores the desktop Copilot pane with explicit controls", () => {
    render(
      <AppShell memberSnapshot={null} initialCopilotMessages={[]}>
        <section>Dashboard content</section>
      </AppShell>,
    );

    expect(
      screen.getByRole("complementary", { name: "Copilot" }),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Hide Copilot" }));

    expect(
      screen.queryByRole("complementary", { name: "Copilot" }),
    ).toBeNull();
    const show = screen.getByRole("button", { name: "Show Copilot" });
    expect(show.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(show);

    fireEvent.click(show);

    expect(
      screen.getByRole("complementary", { name: "Copilot" }),
    ).toBeDefined();
    const hide = screen.getByRole("button", { name: "Hide Copilot" });
    expect(hide.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(hide);
  });
});
