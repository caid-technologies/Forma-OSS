import BlueprintWorkspace from "../../blueprint-workspace";
import { showDeveloperTools } from "../../../lib/server-feature-flags";

type ChatPageProps = {
  params: {
    chatId: string;
  };
};

export default function ChatPage({ params }: ChatPageProps) {
  return <BlueprintWorkspace routeChatId={params.chatId} showDeveloperTools={showDeveloperTools()} />;
}
