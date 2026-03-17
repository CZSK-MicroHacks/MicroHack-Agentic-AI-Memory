# Challenge 07 — Knowledge Graph

## Overview

The Knowledge Graph demo already works: it can run a side-by-side comparison between plain RAG and graph-enhanced agentic search. But the student branch is intentionally "almost there" from a teaching perspective. The comparison still runs, yet it no longer uses the strongest questions and graph reasoning guidance to make the graph advantage obvious.

In this challenge, you will complete the comparison framing so the demo teaches the lesson more clearly:

- plain RAG is good at retrieving relevant nodes
- graph-enhanced search is better for relationship-heavy, community-level, and multi-hop questions

## What's Already in Place

- The runnable solution already exists in `knowledge-graph/`
- The graph data model, traversal logic, and tool-calling agent are already implemented
- The comparison web demo and CLI demo already run two approaches:
  - RAG-only
  - Agentic graph search
- The challenge-ready version of the app lives on the `student-tk` branch
- The `main` branch keeps the completed reference implementation

## Your Task

You need to complete the comparison framing in Python so the graph advantage is easier to understand.

### Part 1: Curate the comparison scenarios

Open `knowledge-graph\api_server.py` and `knowledge-graph\comparison_demo.py`.

Each comparison question should do more than ask a biomedical question. It should also make clear:

- what kind of reasoning is being tested
- why plain RAG struggles here
- what the graph path should reveal

### Part 2: Strengthen graph-aware reasoning guidance

Open `knowledge-graph\agent.py`.

The graph agent should be guided to behave like a graph-aware reasoner:

1. start with relevant search or concept lookup
2. follow graph relationships when the question requires it
3. synthesize the answer using explicit graph evidence

The student branch keeps the mechanics in place, but the comparison is not framed strongly enough until you improve the question set and graph reasoning guidance.

## Files to Inspect

- `knowledge-graph\api_server.py`
- `knowledge-graph\comparison_demo.py`
- `knowledge-graph\agent.py`

## Validation

After implementing both parts:

1. run the comparison demo in the browser or CLI
2. confirm each curated question highlights a distinct graph advantage
3. verify the RAG side still behaves like a baseline, not a graph-aware system
4. verify the graph side uses graph-oriented tool reasoning for the curated scenarios

## Success Criteria

- [ ] The comparison scenarios are curated for teaching, not just execution
- [ ] The comparison questions in the web and CLI demos tell the same story
- [ ] The graph agent prompt encourages search, traversal, and synthesis
- [ ] The curated questions make the graph advantage visible in the existing output
- [ ] The task stays in Python and does not require frontend changes

## Tips

- Keep the implementation small and conceptual
- Do not rebuild the graph logic
- Do not turn the baseline into a graph-aware answer path
- Focus on making the graph advantage easier to observe and explain

If you get blocked, compare your work with:

- `solutions\07-knowledge-graph\README.md`
