"""One-shot, blob-guarded integration for PR #500; never changes an unrecognized base.

Used by the temporary branch-only integration workflow because the authoring
container cannot check out GitHub. The resulting TSX changes are committed as
normal source, not applied at build/runtime. Safe to run again after integration.
"""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps/web/app/forma-workspace.tsx"
HOME = ROOT / "apps/web/app/forma-workspace/home-chat-view.tsx"
MARKER = "chat-project-layout"


def read_guarded(path: Path, expected: str) -> str:
    raw = path.read_bytes()
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if sha != expected:
        raise RuntimeError(f"Refusing to modify {path.name}: expected {expected}, found {sha}")
    return raw.decode()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one integration anchor: {old[:100]!r}")
    return text.replace(old, new, 1)


def integrate() -> None:
    if MARKER in WORKSPACE.read_text() and MARKER in HOME.read_text():
        print("UI integration already committed; no changes needed.")
        return
    workspace = read_guarded(WORKSPACE, "b75a379f7d9af68ef40f4f973cbd3ab383d967e0")
    home = read_guarded(HOME, "b059d6d1a84403aa658f245f5dbc8b5d8e08a89b")
    workspace = replace_once(workspace, 'import HomeChatView from "./forma-workspace/home-chat-view";',
        'import HomeChatView from "./forma-workspace/home-chat-view";\n'
        'import ChatProjectLayout, { ChatProjectSurface, ProjectUpdateCard } from "./forma-workspace/chat-project-layout";')
    workspace = replace_once(workspace, "              projectArtifact={\n", "              projectArtifactId={inlineChatProjectId}\n              projectArtifact={\n")

    start = workspace.index("function ChatWorkspace({")
    end = workspace.index("function scrollableVerticalParent(", start)
    chat = workspace[start:end]
    artifact_match = re.search(r"\n                <ChatProjectArtifact\n.*?\n                />", chat, re.S)
    if artifact_match is None or chat.count("<ChatProjectArtifact") != 1:
        raise RuntimeError("Expected exactly one inline project artifact in ChatWorkspace")
    artifact = artifact_match.group(0).strip()
    chat = chat[:artifact_match.start()] + chat[artifact_match.end():]
    chat = replace_once(chat, "\n  return (\n", "\n  return (\n    <ChatProjectLayout\n      conversationKey={chatId || projectId || \"project-chat\"}\n      projectId={projectId}\n      project={canChat ? (\n        " + artifact + "\n      ) : null}\n    >\n")
    if not chat.endswith("    </div>\n  );\n}\n\n"):
        raise RuntimeError("Unexpected ChatWorkspace return boundary")
    chat = chat[:-len("  );\n}\n\n")] + "    </ChatProjectLayout>\n  );\n}\n\n"
    pipeline = """                          {!message.projectId && (
                            <AgentPipelineProgressView progress={message.pipelineProgress} status={message.status} compact />
                          )}"""
    chat = replace_once(chat, pipeline, pipeline + "\n                          <ProjectUpdateCard message={message} />")
    workspace = workspace[:start] + chat + workspace[end:]

    helper_start = workspace.index("function scrollableVerticalParent(")
    artifact_start = workspace.index("function ChatProjectArtifact({", helper_start)
    panel_start = workspace.index("function ProjectWorkspacePanel({", artifact_start)
    old_artifact = workspace[artifact_start:panel_start]
    signature_end = old_artifact.index(") {\n") + len(") {\n")
    new_artifact = old_artifact[:signature_end] + '''  return (
    <ChatProjectSurface
      title={(
        <EditableWorkspaceTitle
          value={projectTitle}
          canEdit={canEdit && Boolean(onRenameTitle)}
          label="Project title"
          element="div"
          className="truncate text-xs font-semibold text-[var(--forma-text-strong)]"
          onCommit={(title) => onRenameTitle?.(title)}
        />
      )}
    >
      <ProjectWorkspacePanel
        projectId={projectId}
        namespaceTabs={namespaceTabs}
        activeNamespace={activeNamespace}
        onNamespaceChange={onNamespaceChange}
      >
        {projectContent}
      </ProjectWorkspacePanel>
    </ChatProjectSurface>
  );
}

'''
    workspace = workspace[:helper_start] + new_artifact + workspace[panel_start:]
    if workspace.count("useLayoutEffect") == 1:
        workspace = workspace.replace("useLayoutEffect, ", "", 1)
    for name in ("Maximize2", "Minimize2"):
        if len(re.findall(rf"\b{name}\b", workspace)) == 1:
            workspace = workspace.replace(f"  {name},\n", "", 1)

    home = replace_once(home, 'import useChatAutoScroll from "./use-chat-auto-scroll";',
        'import useChatAutoScroll from "./use-chat-auto-scroll";\n'
        'import ChatProjectLayout, { ProjectUpdateCard } from "./chat-project-layout";')
    home = replace_once(home, "  projectArtifact?: ReactNode;", "  projectArtifact?: ReactNode;\n  projectArtifactId?: string | null;")
    home = replace_once(home, "  projectArtifact,\n", "  projectArtifact,\n  projectArtifactId = null,\n")
    home = replace_once(home, "  return (\n    <section", "  return (\n    <ChatProjectLayout conversationKey={conversationKey} projectId={projectArtifactId} project={started ? projectArtifact : null}>\n    <section")
    home = replace_once(home, "            {projectArtifact}\n", "")
    home = replace_once(home, "                    {!message.projectId && renderPipelineProgress(message)}", "                    {!message.projectId && renderPipelineProgress(message)}\n                    <ProjectUpdateCard message={message} />")
    form_start = home.index("        <form\n          onSubmit={onSubmit}\n")
    form_end = home.index("\n        >", form_start)
    home = home[:form_start] + '''        <form
          onSubmit={onSubmit}
          className={started
            ? "relative z-10 max-h-[45dvh] w-full shrink-0 overflow-y-auto overscroll-contain px-3 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1 sm:px-4 md:pb-3"
            : "fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain bg-transparent px-3 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1 sm:px-4 md:static md:order-1 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible md:bg-transparent md:p-0"}
''' .rstrip() + home[form_end:]
    home = replace_once(home, "    </section>\n  );\n}", "    </section>\n    </ChatProjectLayout>\n  );\n}")
    WORKSPACE.write_text(workspace)
    HOME.write_text(home)
    print("Integrated shared project workspace into both chat entry points.")


if __name__ == "__main__":
    integrate()
