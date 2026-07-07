import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConversationFeed from "../components/ConversationFeed";
import { makeMessage, mockFetch, page, renderWithProviders } from "./utils";

describe("ConversationFeed", () => {
  it("renders agent messages with sender, type, and recipient", async () => {
    mockFetch({
      "GET /projects/proj-1/messages": page([
        makeMessage({ sender_name: "Cleo CEO", content: "The vision is set." }),
        makeMessage({
          sender_name: "Quinn QA",
          sender_agent_key: "qa_engineer",
          recipient_name: "Bo Backend",
          message_type: "revision_request",
          content: "Changes requested: fix the login endpoint.",
        }),
      ]),
    });
    renderWithProviders(<ConversationFeed projectId="proj-1" />);

    expect(await screen.findByText("The vision is set.")).toBeInTheDocument();
    expect(screen.getByText("Cleo CEO")).toBeInTheDocument();
    expect(screen.getByText("→ Bo Backend")).toBeInTheDocument();
    expect(screen.getByText("revision request")).toBeInTheDocument();
    expect(screen.getAllByTestId("message-row")).toHaveLength(2);
  });

  it("labels system messages as Company", async () => {
    mockFetch({
      "GET /projects/proj-1/messages": page([
        makeMessage({
          sender_name: null,
          sender_agent_key: null,
          message_type: "system",
          content: "Kickoff: the company is now working.",
        }),
      ]),
    });
    renderWithProviders(<ConversationFeed projectId="proj-1" />);
    expect(await screen.findByText("Company")).toBeInTheDocument();
  });

  it("shows the quiet empty state", async () => {
    mockFetch({ "GET /projects/proj-1/messages": page([]) });
    renderWithProviders(<ConversationFeed projectId="proj-1" />);
    expect(await screen.findByText(/hasn't started talking yet/)).toBeInTheDocument();
  });
});
