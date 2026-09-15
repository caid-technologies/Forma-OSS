import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import ProjectExportsPanel from "../../app/forma-workspace/project-exports-panel";
import FabricationSettingsCard from "../../components/fabrication-settings";
import { AuthFixture } from "./fabrication-auth";
import "./chat-project-workspace.css";

function Fixture() {
  const [project, setProject] = useState("project-one");
  const [accountView, setAccountView] = useState(false);
  return <AuthFixture>
    <button onClick={() => setProject("project-two")}>Other project</button>
    <button onClick={() => setAccountView((value) => !value)}>Toggle account settings</button>
    {accountView ? <FabricationSettingsCard /> : <ProjectExportsPanel projectId={project} />}
  </AuthFixture>;
}
createRoot(document.getElementById("root")!).render(<StrictMode><Fixture /></StrictMode>);
