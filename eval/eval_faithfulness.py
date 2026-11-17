"""Answer faithfulness: answer each golden question from the retrieved chunks, then let the
Sidekick's own evaluator judge whether every claim is supported and cited. PAID: 40 gpt-5.4-mini calls.

Run with: uv run python -m eval.eval_faithfulness
"""

import asyncio
import json
from pathlib import Path

from langchain_openai import ChatOpenAI

import knowledge_base as kb
from sidekick import EvaluatorOutput, Sidekick
from sidekick_tools import format_results

GOLDEN = json.loads((Path(__file__).parent / "golden_set.json").read_text())
CRITERIA = ("Every claim in the reply is supported by the retrieved chunks and cited with its [file#chunk] label. "
            "Saying the knowledge base does not cover it also passes, if that is true.")


async def main():
    llm = ChatOpenAI(model="gpt-5.4-mini")
    judge = Sidekick()  # no setup(): we only need its evaluator, not the MCP servers
    judge.evaluator = llm.with_structured_output(EvaluatorOutput)
    passed = 0
    for item in GOLDEN:
        context = format_results(kb.search(item["question"], k=5))
        reply = (await llm.ainvoke(
            f"Answer only from these chunks and cite each claim like [pep8.md#11].\n\n{context}\n\nQuestion: {item['question']}"
        )).content
        # the judge sees the chunks as part of the request, so it can check support
        verdict = await judge.evaluate(f"{item['question']}\n\nRetrieved chunks:\n{context}", CRITERIA, reply,
                                       ["search_knowledge_base"])
        passed += verdict.success_criteria_met
        print("PASS" if verdict.success_criteria_met else "FAIL", item["question"], "|", verdict.feedback[:100])
    print(f"\nFaithfulness: {passed}/{len(GOLDEN)} = {passed / len(GOLDEN):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
