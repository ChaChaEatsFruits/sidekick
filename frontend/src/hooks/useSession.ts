import { useEffect, useState } from "react";
import type { Snapshot } from "../api";

// One Server-Sent Events connection; every event is the whole session state, so a reconnect
// after a dropped connection (or a backend restart) brings the page fully up to date.
export function useSession(): { session: Snapshot | null; connected: boolean } {
  const [session, setSession] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const stream = new EventSource("/api/stream");
    stream.onmessage = (event) => {
      setConnected(true);
      setSession(JSON.parse(event.data) as Snapshot);
    };
    stream.onerror = () => setConnected(false); // EventSource retries by itself
    return () => stream.close();
  }, []);

  return { session, connected };
}
