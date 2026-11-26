import { useState, type FormEvent, type KeyboardEvent } from "react";
import { startTask } from "../api";

export function TaskForm({ canStart }: { canStart: boolean }) {
  const [message, setMessage] = useState("");
  const [criteria, setCriteria] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const ready = canStart && !sending && message.trim() !== "";

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!ready) return;
    setSending(true);
    setError(null);
    try {
      await startTask(message, criteria);
      setMessage(""); // keep the criteria: follow-up tasks often share them
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
  }

  return (
    <form className="task" onSubmit={submit}>
      <label>
        <span>Task</span>
        <textarea
          rows={2}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Find flights from Chennai to Singapore on 14 December and save the three cheapest to a file"
        />
      </label>
      <label>
        <span>Done when</span>
        <input
          value={criteria}
          onChange={(e) => setCriteria(e.target.value)}
          placeholder="The file lists airline, times and price for each flight"
        />
      </label>
      <button type="submit" disabled={!ready}>Start task</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
