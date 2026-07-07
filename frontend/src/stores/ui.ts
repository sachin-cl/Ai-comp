import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  theme: "dark" | "light";
  toggleTheme: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "dark",
      toggleTheme: () =>
        set((s) => {
          const theme = s.theme === "dark" ? "light" : "dark";
          document.documentElement.classList.toggle("dark", theme === "dark");
          return { theme };
        }),
    }),
    {
      name: "ai-company-ui",
      onRehydrateStorage: () => (state) => {
        document.documentElement.classList.toggle("dark", state?.theme !== "light");
      },
    },
  ),
);
