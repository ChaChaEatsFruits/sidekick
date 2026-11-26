import { reset, type Status } from "./api";
import { ApprovalBanner } from "./components/ApprovalBanner";
import { Chat } from "./components/Chat";
import { KnowledgeBase } from "./components/KnowledgeBase";
import { PlanPanel } from "./components/PlanPanel";
import { TaskForm } from "./components/TaskForm";
import { useSession } from "./hooks/useSession";

const STATUS_TEXT: Record<Status, string> = {
  starting: "Starting the browser and tools",
  ready: "Ready",
  running: "Working",
  paused: "Needs your go-ahead",
  error: "Something went wrong",
};

export function App() {
  const { session, connected } = useSession();
  const status = session?.status;
  const pending = session?.messages.slice().reverse().find((m) => m.content.startsWith("Waiting for your approval:"));

  function onReset() {
    const busy = status === "running" || status === "paused";
    if (!busy || window.confirm("Stop the current task and start a fresh Sidekick?")) reset();
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Sidekick</h1>
          <div className="brand-bar" />
        </div>
        <span className={`status ${connected ? status : "offline"}`}>
          {connected && status ? STATUS_TEXT[status] : "Connecting to the Sidekick"}
        </span>
        <button className="secondary" onClick={onReset} disabled={!connected}>Reset</button>
      </header>

      <main>
        <Chat messages={session?.messages ?? []} working={status === "running"} />
        <aside>
          <PlanPanel plan={session?.plan ?? []} />
          <KnowledgeBase />
        </aside>
      </main>

      <footer>
        {status === "paused" && pending && <ApprovalBanner request={pending.content} />}
        {session?.error && <p className="error banner">{session.error}</p>}
        <TaskForm canStart={connected && (status === "ready" || status === "error")} />
      </footer>
    </div>
  );
}
