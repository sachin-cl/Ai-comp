import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { useAuthStore } from "../stores/auth";

// jsdom doesn't implement scrollIntoView (used by the conversation feed).
Element.prototype.scrollIntoView = () => {};

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, user: null });
  localStorage.clear();
});
