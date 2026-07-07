import { useMemo, useState } from "react";
import Prism from "prismjs";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-docker";
import "prismjs/components/prism-markdown";
import { useArtifact, useArtifactVersions, useProjectArtifacts } from "../api/hooks";
import type { Artifact } from "../types";

const PRISM_LANG: Record<string, string> = {
  typescript: "tsx",
  javascript: "jsx",
  tsx: "tsx",
  jsx: "jsx",
  python: "python",
  sql: "sql",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  dockerfile: "docker",
  markdown: "markdown",
  html: "markup",
  bash: "bash",
  shell: "bash",
};

interface TreeNode {
  name: string;
  path: string;
  artifact?: Artifact;
  children: Map<string, TreeNode>;
}

function buildTree(artifacts: Artifact[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: new Map() };
  for (const artifact of artifacts) {
    const parts = artifact.path.split("/");
    let node = root;
    let acc = "";
    for (let i = 0; i < parts.length; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i];
      if (!node.children.has(parts[i])) {
        node.children.set(parts[i], { name: parts[i], path: acc, children: new Map() });
      }
      node = node.children.get(parts[i])!;
      if (i === parts.length - 1) node.artifact = artifact;
    }
  }
  return root;
}

function TreeView({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selected: string | null;
  onSelect: (a: Artifact) => void;
}) {
  const dirs = [...node.children.values()].filter((n) => !n.artifact);
  const files = [...node.children.values()].filter((n) => n.artifact);
  return (
    <div>
      {[...dirs, ...files].map((child) => (
        <div key={child.path}>
          {child.artifact ? (
            <button
              className={`flex w-full items-center gap-1.5 truncate rounded px-2 py-1 text-left text-sm hover:bg-slate-100 dark:hover:bg-surface-lighter ${
                selected === child.artifact.id ? "bg-accent/10 text-accent" : ""
              }`}
              style={{ paddingLeft: `${depth * 14 + 8}px` }}
              onClick={() => onSelect(child.artifact!)}
              data-testid="file-node"
            >
              📄 <span className="truncate">{child.name}</span>
              {child.artifact.validation_ok === false && (
                <span title="static validation issues">⚠️</span>
              )}
            </button>
          ) : (
            <>
              <div
                className="flex items-center gap-1.5 px-2 py-1 text-sm font-medium text-slate-600 dark:text-slate-300"
                style={{ paddingLeft: `${depth * 14 + 8}px` }}
              >
                📁 {child.name}
              </div>
              <TreeView node={child} depth={depth + 1} selected={selected} onSelect={onSelect} />
            </>
          )}
        </div>
      ))}
    </div>
  );
}

export default function FileExplorer({ projectId }: { projectId: string }) {
  const { data: artifacts, isLoading } = useProjectArtifacts(projectId);
  const [selected, setSelected] = useState<Artifact | null>(null);
  const { data: content } = useArtifact(selected?.id ?? null);
  const { data: versions } = useArtifactVersions(selected?.id ?? null);
  const tree = useMemo(() => buildTree(artifacts ?? []), [artifacts]);

  const highlighted = useMemo(() => {
    if (!content) return "";
    const lang = PRISM_LANG[content.language.toLowerCase()] ?? null;
    if (lang && Prism.languages[lang]) {
      return Prism.highlight(content.content, Prism.languages[lang], lang);
    }
    return Prism.util.encode(content.content).toString();
  }, [content]);

  if (isLoading) return <div className="card animate-pulse">Loading files…</div>;
  if (!artifacts?.length)
    return (
      <div className="card py-10 text-center text-slate-500">
        No files yet — the engineers haven't delivered their first artifacts.
      </div>
    );

  return (
    <div className="grid gap-4 lg:grid-cols-[280px,1fr]">
      <div className="card max-h-[65vh] overflow-y-auto p-2">
        <TreeView node={tree} depth={0} selected={selected?.id ?? null} onSelect={setSelected} />
      </div>
      <div className="card max-h-[65vh] overflow-auto p-0">
        {!content ? (
          <div className="p-10 text-center text-slate-500">Select a file to view it.</div>
        ) : (
          <>
            <div className="sticky top-0 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-2 text-xs backdrop-blur dark:border-slate-700 dark:bg-surface-light/90">
              <span className="font-mono font-medium">{content.path}</span>
              <span className="badge bg-slate-100 dark:bg-surface-lighter">
                v{content.version}
              </span>
              <span>{(content.size_bytes / 1024).toFixed(1)} KB</span>
              {content.validation.ok === false && (
                <span className="text-amber-500">
                  ⚠ {content.validation.issues?.join("; ")}
                </span>
              )}
              {versions && versions.length > 1 && (
                <span className="ml-auto text-slate-400">{versions.length} versions kept</span>
              )}
            </div>
            <pre className="overflow-x-auto bg-slate-950 p-4">
              <code
                className={`language-${content.language}`}
                dangerouslySetInnerHTML={{ __html: highlighted }}
              />
            </pre>
          </>
        )}
      </div>
    </div>
  );
}
