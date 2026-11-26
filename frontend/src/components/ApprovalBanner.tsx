import { useState } from "react";
import { approve } from "../api";

// Shown while the agent is paused before a sensitive action (a push notification, or asking
// you to do something in its browser window). Nothing runs until you choose.
export function ApprovalBanner({ request }: { request: string }) {
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function decide(yes: boolean) {
    setSending(true);
    setError(null);
    try {
      await approve(yes);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="approval" role="alert">
      <div>
        <strong>The Sidekick needs your go-ahead</strong>
        <p>{request.replace("Waiting for your approval:", "").trim()}</p>
        {error && <p className="error">{error}</p>}
      </div>
      <div className="actions">
        <button className="secondary" disabled={sending} onClick={() => decide(false)}>Deny</button>
        <button className="gold" disabled={sending} onClick={() => decide(true)}>Approve</button>
      </div>
    </section>
  );
}
