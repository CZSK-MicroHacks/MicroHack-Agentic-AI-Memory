# Solution 06 — Agents Scratchpad

This solution explains the intended fix for the student version of `multi-agent/` on the `student-tk` branch.

## The intended bug

The student branch is designed so that:

- specialist agents still write into the shared scratchpad
- the facilitator still creates and tracks tasks
- but the facilitator does **not** complete the final merge/review pass

That means students can see collaboration happening, but they also see why shared memory needs orchestration and synthesis.

## Root cause

Two facilitator-facing pieces are intentionally incomplete:

1. `multi-agent\backend\tools.py`
2. `multi-agent\backend\prompts\facilitator.j2`

The missing behavior is not about specialist agents. It is about the facilitator being unable or unlikely to finish the scratchpad lifecycle.

## What students are expected to restore

### Part 1: Facilitator tool exposure

In `FacilitatorTools.all`, the facilitator should have access to the tools needed to:

- consolidate document sections
- read the clean final document

The completed version exposes:

```python
@property
def all(self) -> list:
    return [
        self.create_tasks,
        self.get_plan_status,
        self.read_document,
        self.consolidate_section,
        self.read_document_clean,
    ]
```

### Part 2: Facilitator instructions

The prompt in `multi-agent\backend\prompts\facilitator.j2` should explicitly tell the facilitator to:

- wait until tasks are finished
- read the document
- consolidate entries where needed
- run a final clean review
- only then answer the user

The important ideas to restore are:

- a consolidation phase after specialist execution
- a final review phase using `read_document_clean`
- a rule that the final answer must come from the reviewed document, not from raw intermediate entries

## Why this is the right fix

This challenge is about the **shared scratchpad pattern**, not about adding another agent or building new UI.

The real lesson is:

- specialists create candidate content
- the facilitator turns that shared working state into a coherent final artifact

## Acceptance check

After the fix, the workflow should behave like this:

1. tasks are created
2. specialists complete their assignments
3. the facilitator reviews and consolidates the shared document
4. the facilitator reads the clean version
5. the final answer reflects the reviewed itinerary

If students restore those two seams, they have completed the challenge.
