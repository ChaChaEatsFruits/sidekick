import { useEffect, useRef } from "react";
import Markdown from "react-markdown";
import { classify, parseSources, type Message } from "../lib/messages";

function Sources({ content }: { content: string }) {
  return (
    <ul className="sources" aria-label="Sources">
      {parseSources(content).map((source) => (
        <li key={source.id} className={source.missing ? "missing" : undefined}>
          <span className="cite">{source.id}</span>
          <span>{source.missing ? "Not in the knowledge base" : source.snippet}</span>
        </li>
      ))}
    </ul>
  );
}

function Entry({ message }: { message: Message }) {
  const kind = classify(message);
  switch (kind) {
    case "user":
      return <div className="msg user">{message.content}</div>;
    case "sources":
      return <Sources content={message.content} />;
    case "evaluator":
    case "metrics":
      return <p className={`msg note ${kind}`}>{message.content}</p>;
    case "approval": // a tool-call description, not markdown
      return <p className="msg asked">{message.content}</p>;
    default:
      return (
        <div className={`msg agent ${kind}`}>
          <Markdown components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
            {message.content}
          </Markdown>
        </div>
      );
  }
}

export function Chat({ messages, working }: { messages: Message[]; working: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, working]);

  return (
    <section className="chat" aria-live="polite">
      {messages.length === 0 && (
        <p className="empty">
          Give the Sidekick a task below. It can browse the web in its own window, search your knowledge base,
          and write files to its sandbox.
        </p>
      )}
      {messages.map((message, i) => (
        <Entry key={i} message={message} />
      ))}
      {working && <p className="msg note working">Working on it…</p>}
      <div ref={end} />
    </section>
  );
}
