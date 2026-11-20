"""Retrieval eval: hit rate@k and MRR on the golden set, for several chunk sizes. Local only, $0.

Run with: uv run python -m eval.eval_retrieval
"""

import json
import re
import statistics
import time
from pathlib import Path

import knowledge_base as kb

HERE = Path(__file__).parent
GOLDEN = json.loads((HERE / "golden_set.json").read_text())
CHUNK_SIZES = [300, 800, 1500]
KS = [1, 3, 5]
MAX_K = 10  # MRR looks this deep; a miss past here scores 0
MIN_SCORE = 0.3  # same cutoff the agent tool uses


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()  # PDF text has line breaks mid-sentence


def first_rank(hits: list[dict], relevant) -> int | None:
    """1-based rank of the first relevant hit, or None if none of them is."""
    return next((i + 1 for i, h in enumerate(hits) if relevant(h)), None)


def metrics(ranks: list, prefix: str) -> dict:
    n = len(ranks)
    return {
        **{f"{prefix}@{k}": sum(r is not None and r <= k for r in ranks) / n for k in KS},
        f"{prefix} MRR": sum(1 / r for r in ranks if r) / n,
    }


def evaluate(collection: str) -> dict:
    source_ranks, answer_ranks, latencies, answer_at_5_filtered = [], [], [], 0
    for item in GOLDEN:
        start = time.perf_counter()
        hits = kb.search(item["question"], k=MAX_K, name=collection)
        latencies.append((time.perf_counter() - start) * 1000)
        def has_answer(h, item=item):
            return h["source"] == item["source"] and norm(item["answer"]) in norm(h["text"])

        source_ranks.append(first_rank(hits, lambda h: h["source"] == item["source"]))
        answer_ranks.append(first_rank(hits, has_answer))
        answer_at_5_filtered += any(has_answer(h) and h["score"] >= MIN_SCORE for h in hits[:5])
    return {
        **metrics(source_ranks, "source"),
        **metrics(answer_ranks, "answer"),
        "answer@5 (score>=0.3)": answer_at_5_filtered / len(GOLDEN),
        "p50 ms": statistics.median(latencies),
        "misses": [g["question"] for g, r in zip(GOLDEN, answer_ranks) if r is None or r > 5],
    }


if __name__ == "__main__":
    kb.search("warm up", k=1)  # load the embedding model before timing anything
    rows = []
    for size in CHUNK_SIZES:
        name = f"eval_{size}"
        chunks = kb.build_index(name=name, chunk_size=size, overlap=size * 15 // 100)
        rows.append({"chunk size": size, "chunks": chunks, **evaluate(name)})

    cols = ["chunk size", "chunks", "source@1", "source@5", "source MRR",
            *[f"answer@{k}" for k in KS], "answer MRR", "answer@5 (score>=0.3)", "p50 ms"]

    def fmt(col, v):
        return f"{v:.0%}" if "@" in col else f"{v:.2f}" if isinstance(v, float) else str(v)

    table = "\n".join(
        ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        + ["| " + " | ".join(fmt(c, r[c]) for c in cols) + " |" for r in rows]
    )
    misses = "\n".join(f"- chunk {r['chunk size']}: {q}" for r in rows for q in r["misses"])
    report = f"# Retrieval eval ({len(GOLDEN)} questions, {kb.EMBEDDING_MODEL})\n\n{table}\n\n## Misses at k=5\n\n{misses or 'none'}\n"
    (HERE / "results.md").write_text(report)
    print(report)
