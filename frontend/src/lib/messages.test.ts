import { describe, expect, it } from "vitest";
import { classify, parseSources } from "./messages";

describe("classify", () => {
  it("tells the user's messages from the agent's", () => {
    expect(classify({ role: "user", content: "Sources:\nnot really" })).toBe("user");
    expect(classify({ role: "assistant", content: "Here is what I found." })).toBe("answer");
  });

  it("recognises the agent's status lines by their prefix", () => {
    expect(classify({ role: "assistant", content: "Sources:\n- **pep8.md#11**: Limit lines…" })).toBe("sources");
    expect(classify({ role: "assistant", content: "Evaluator: criteria met" })).toBe("evaluator");
    expect(classify({ role: "assistant", content: "Metrics: 1,200 in / 300 out tokens" })).toBe("metrics");
    expect(classify({ role: "assistant", content: "Waiting for your approval:\nsend a push" })).toBe("approval");
  });
});

describe("parseSources", () => {
  it("reads each citation, flagging ones missing from the knowledge base", () => {
    const content = "Sources:\n- **pep8.md#11**: Limit all lines to 79 characters.…\n- **made_up.md#9**: ⚠ not in the knowledge base";
    expect(parseSources(content)).toEqual([
      { id: "pep8.md#11", snippet: "Limit all lines to 79 characters.…", missing: false },
      { id: "made_up.md#9", snippet: "⚠ not in the knowledge base", missing: true },
    ]);
  });

  it("returns nothing for text that is not a sources list", () => {
    expect(parseSources("Just an answer with **bold**: text")).toEqual([]);
  });
});
