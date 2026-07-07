const EMOJI: Record<string, string> = {
  ceo: "🎩",
  ceo_approval: "🎩",
  product_manager: "📋",
  architect: "📐",
  designer: "🎨",
  frontend_engineer: "🖥️",
  backend_engineer: "🔧",
  database_engineer: "🗄️",
  devops_engineer: "🚀",
  qa_engineer: "🔍",
  security_engineer: "🛡️",
  technical_writer: "✍️",
  marketing_manager: "📣",
};

export default function AgentAvatar({
  agentKey,
  size = "md",
}: {
  agentKey: string | null | undefined;
  size?: "sm" | "md" | "lg";
}) {
  const sizes = { sm: "h-6 w-6 text-sm", md: "h-9 w-9 text-lg", lg: "h-14 w-14 text-3xl" };
  return (
    <span
      className={`flex ${sizes[size]} shrink-0 items-center justify-center rounded-full bg-slate-200 dark:bg-surface-lighter`}
      title={agentKey ?? "system"}
    >
      {agentKey ? (EMOJI[agentKey] ?? "🤖") : "🏢"}
    </span>
  );
}
