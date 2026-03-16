# Solution 07 — Knowledge Graph

This solution explains the intended implementation for the challenge-ready version of `knowledge-graph/` on the `student-tk` branch.

## The intended gap

The comparison demo already works mechanically:

- the RAG baseline runs
- the graph agent runs
- tool traces and answers are shown

But the teaching signal is too weak. A student can see two answers, yet still miss *why* the graph path is better for certain classes of questions.

## What students are expected to complete

### Part 1: Curated comparison framing

The comparison questions should be intentionally chosen to expose graph strengths, for example:

- shared connections between two entities
- community or landscape questions
- multi-hop relationship questions
- interaction-heavy safety questions

The completed version uses curated question sets in:

- `knowledge-graph\api_server.py`
- `knowledge-graph\comparison_demo.py`

That makes the comparison intentional instead of generic.

### Part 2: Graph-aware prompt guidance

The completed version also keeps strong graph reasoning guidance in:

- `knowledge-graph\agent.py`

The important ideas in the completed prompt are:

- start from search
- traverse the graph when relationships matter
- make multiple tool calls when needed
- cite specific graph relationships in the final answer

## Completed implementation shape

The finished version is intentionally lightweight and Python-only:

- curated comparison questions in `api_server.py`
- matching curated comparison questions in `comparison_demo.py`
- a graph-oriented system prompt in `agent.py`

## Why this is the right challenge

Challenge 07 should primarily teach:

- when graph-enhanced search matters
- how graph structure changes the answer quality

It should **not** primarily be a React task or an AGE setup task.

## Acceptance check

After the fix:

1. each comparison question has a clear teaching purpose
2. the baseline still behaves like flat retrieval
3. the graph path uses search + traversal for the curated scenarios
4. the CLI and web comparison surfaces tell the same story

Completing those seams resolves the challenge.
