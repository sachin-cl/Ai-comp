import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "../pages/LoginPage";
import { useAuthStore } from "../stores/auth";
import { mockFetch, renderWithProviders } from "./utils";

const TOKENS = {
  access_token: "access-abc",
  refresh_token: "refresh-def",
  token_type: "bearer",
  expires_in: 900,
};

function renderLogin() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<div>DASHBOARD HOME</div>} />
    </Routes>,
    { route: "/login" },
  );
}

describe("LoginPage", () => {
  it("renders the sign-in form", () => {
    mockFetch({});
    renderLogin();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /register/i })).toBeInTheDocument();
  });

  it("logs in, stores tokens, and navigates to the dashboard", async () => {
    const calls = mockFetch({ "POST /auth/login": TOKENS });
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText("DASHBOARD HOME")).toBeInTheDocument());
    expect(calls).toContainEqual({
      url: "/auth/login",
      method: "POST",
      body: { email: "user@example.com", password: "password123" },
    });
    expect(useAuthStore.getState().accessToken).toBe("access-abc");
    expect(useAuthStore.getState().refreshToken).toBe("refresh-def");
  });

  it("shows the API error message on bad credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: async () => ({
          error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password" },
        }),
        blob: async () => new Blob(),
      })),
    );
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
});
