# Retrieval eval (20 questions, all-MiniLM-L6-v2)

| chunk size | chunks | source@1 | source@5 | source MRR | answer@1 | answer@3 | answer@5 | answer MRR | answer@5 (score>=0.3) | p50 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| 300 | 1362 | 90% | 95% | 0.93 | 35% | 80% | 80% | 0.56 | 80% | 18.75 |
| 800 | 479 | 90% | 90% | 0.90 | 55% | 75% | 75% | 0.65 | 75% | 20.84 |
| 1500 | 244 | 90% | 95% | 0.92 | 50% | 75% | 80% | 0.63 | 80% | 18.66 |

## Misses at k=5

- chunk 300: How many blank lines go around top-level function and class definitions?
- chunk 300: How do I annotate a function argument that can be either an int or None?
- chunk 300: What motivated adding a way to assign variables inside an expression?
- chunk 300: Is being explicit preferred over being implicit in Python's design philosophy?
- chunk 800: Should docstrings use single or triple double quotes?
- chunk 800: How do I annotate a function argument that can be either an int or None?
- chunk 800: What motivated adding a way to assign variables inside an expression?
- chunk 800: Is being explicit preferred over being implicit in Python's design philosophy?
- chunk 800: What does Python's guiding philosophy say about letting errors pass silently?
- chunk 1500: When wrapping a long arithmetic expression, should the line break go before or after the operator?
- chunk 1500: How do I annotate a function argument that can be either an int or None?
- chunk 1500: Is it allowed to write x := 5 as a statement on its own without parentheses?
- chunk 1500: What does Python's guiding philosophy say about letting errors pass silently?

## Answer faithfulness (gpt-5.4-mini answers from top-5 chunks at chunk size 800, judged by Sidekick.evaluate)

**18/20 = 90%** supported and cited. Both failures (int-or-None, explicit-vs-implicit) are questions where retrieval missed the answer chunk, and the model filled the gap from its own knowledge. Per-question log: eval/faithfulness.txt
