import BlueprintWorkspace from "../../blueprint-workspace";
import { deployedAuthRequired } from "../../../lib/deployed-auth";
import { showDeveloperTools } from "../../../lib/server-feature-flags";

type ChatPageProps = {
  params: {
    chatId: string;
  };
};

export default function ChatPage({ params }: ChatPageProps) {
  return <BlueprintWorkspace authRequired={deployedAuthRequired()} routeChatId={params.chatId} showDeveloperTools={showDeveloperTools()} />;
}
