import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import FileExplorer from "../components/FileExplorer";
import { mockFetch, renderWithProviders } from "./utils";

const ARTIFACTS = [
  {
    id: "art-1",
    path: "backend/main.py",
    language: "python",
    latest_version: 2,
    size_bytes: 120,
    validation_ok: true,
    updated_at: "2026-07-07T10:00:00Z",
  },
  {
    id: "art-2",
    path: "backend/models.py",
    language: "python",
    latest_version: 1,
    size_bytes: 60,
    validation_ok: false,
    updated_at: "2026-07-07T10:00:00Z",
  },
];

const CONTENT = {
  id: "art-1",
  path: "backend/main.py",
  language: "python",
  version: 2,
  content: "from fastapi import FastAPI\napp = FastAPI()\n",
  content_hash: "abc123",
  size_bytes: 120,
  validation: { tool: "python-ast", ok: true, issues: [] },
  created_at: "2026-07-07T10:00:00Z",
};

describe("FileExplorer", () => {
  it("shows the empty state before any artifacts exist", async () => {
    mockFetch({ "GET /projects/proj-1/artifacts": [] });
    renderWithProviders(<FileExplorer projectId="proj-1" />);
    expect(await screen.findByText(/No files yet/)).toBeInTheDocument();
  });

  it("builds a directory tree from artifact paths", async () => {
    mockFetch({ "GET /projects/proj-1/artifacts": ARTIFACTS });
    renderWithProviders(<FileExplorer projectId="proj-1" />);

    expect(await screen.findByText("main.py")).toBeInTheDocument();
    const files = screen.getAllByTestId("file-node");
    expect(files).toHaveLength(2);
    // Folder row shows the directory name (rendered as "📁 backend").
    expect(
      screen.getByText((_, el) => el?.textContent?.trim() === "📁 backend"),
    ).toBeInTheDocument();
    expect(screen.getByText("Select a file to view it.")).toBeInTheDocument();
  });

  it("opens a file with version info and highlighted content", async () => {
    mockFetch({
      "GET /projects/proj-1/artifacts": ARTIFACTS,
      "GET /artifacts/art-1": CONTENT,
      "GET /artifacts/art-1/versions": [
        { version: 2, content_hash: "abc", size_bytes: 120, validation_ok: true },
        { version: 1, content_hash: "def", size_bytes: 100, validation_ok: true },
      ],
    });
    renderWithProviders(<FileExplorer projectId="proj-1" />);

    await userEvent.click(await screen.findByText("main.py"));
    expect(await screen.findByText("backend/main.py")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("2 versions kept")).toBeInTheDocument();
    // Prism split the code into tokens; assert on a stable fragment.
    expect(document.querySelector("code.language-python")?.textContent).toContain("FastAPI");
  });
});
