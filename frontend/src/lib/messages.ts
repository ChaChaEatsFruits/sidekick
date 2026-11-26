// The agent's chat history is a list of plain {role, content} strings. Besides answers, it adds
// status lines with fixed prefixes (see sidekick.py); the chat renders each kind differently.

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export type Kind = "user" | "answer" | "sources" | "evaluator" | "metrics" | "approval";

const PREFIXES: [string, Kind][] = [
  ["Sources:\n", "sources"],
  ["Evaluator: ", "evaluator"],
  ["Metrics: ", "metrics"],
  ["Waiting for your approval:", "approval"],
];

export function classify(message: Message): Kind {
  if (message.role === "user") return "user";
  return PREFIXES.find(([prefix]) => message.content.startsWith(prefix))?.[1] ?? "answer";
}

export interface Source {
  id: string;
  snippet: string;
  missing: boolean;
}

// cited_sources() in sidekick.py writes one line per citation: "- **file#chunk**: snippet…"
const SOURCE_LINE = /^- \*\*([^*]+#\d+)\*\*: (.*)$/;

export function parseSources(content: string): Source[] {
  return content.split("\n").flatMap((line) => {
    const match = SOURCE_LINE.exec(line);
    return match ? [{ id: match[1], snippet: match[2], missing: match[2].startsWith("⚠") }] : [];
  });
}
