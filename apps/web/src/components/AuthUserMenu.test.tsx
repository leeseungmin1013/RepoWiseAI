import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthUserMenu } from "./AuthUserMenu";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
  signOut: vi.fn().mockResolvedValue({ error: null }),
  unsubscribe: vi.fn(),
  getSession: vi.fn().mockResolvedValue({
    data: { session: { user: { email: "learner@example.com" } } },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

vi.mock("@/lib/supabase/client", () => ({
  getSupabaseBrowserClient: () => ({
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe: mocks.unsubscribe } },
      }),
      signOut: mocks.signOut,
    },
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthUserMenu", () => {
  it("shows the signed-in account and supports logout", async () => {
    render(<AuthUserMenu />);

    expect(await screen.findByText("learner@example.com")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /learner@example.com/ }).getAttribute("href"),
    ).toBe("/account");
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    await waitFor(() => expect(mocks.signOut).toHaveBeenCalledOnce());
    expect(mocks.replace).toHaveBeenCalledWith("/login");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it("unsubscribes from auth changes when removed", async () => {
    const view = render(<AuthUserMenu />);
    await screen.findByText("learner@example.com");
    view.unmount();
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });
});