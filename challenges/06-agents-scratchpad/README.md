# Challenge 06 — Agents Scratchpad

## Overview

The multi-agent travel planner already works — the facilitator creates tasks, specialist agents run, and the shared scratchpad fills with itinerary ideas. But the workflow stops too early: the facilitator never completes the final merge/review phase.

In this challenge, you will restore the missing facilitator behavior so the shared scratchpad becomes a reviewed final itinerary instead of just a raw collaboration space.

After completing this challenge, students should understand the main message of multi-agent shared memory:

- specialists write intermediate ideas into shared memory
- the facilitator comes back to reconcile those ideas into a final version

## What's Already in Place

- The runnable app already exists in `multi-agent/`
- The architecture is documented in `multi-agent\README.md`
- The shared scratchpad implementation already exists:
  - `TaskBoard` for coordination
  - `SharedDocument` for the versioned itinerary
- Specialist agents already:
  - read assigned tasks
  - write candidate content into the shared document
  - mark tasks complete
- The facilitator already:
  - creates tasks
  - dispatches specialists
  - checks progress
- The **student version** of the app lives on the `student-tk` branch
- The `main` branch keeps the completed reference implementation

## Your Task

You need to restore two small but important pieces of the facilitator workflow.

### Part 1: Restore facilitator tool access

Open `multi-agent\backend\tools.py` and inspect `FacilitatorTools`.

The facilitator should have access to the tools needed to:

- consolidate document sections
- read the clean final document before answering

In the student branch, that final facilitator tool access is intentionally incomplete.

### Part 2: Restore facilitator instructions

Open `multi-agent\backend\prompts\facilitator.j2`.

The facilitator prompt should clearly instruct the agent to:

1. wait until tasks are completed
2. review the shared document
3. consolidate entries where needed
4. perform a final clean review
5. only then present the answer to the user

In the student branch, the prompt has been simplified so the facilitator stops before the real merge/review phase.

## Files to Inspect

- `multi-agent\backend\tools.py`
- `multi-agent\backend\prompts\facilitator.j2`
- `multi-agent\README.md`

## Validation

After implementing both parts:

1. Start the backend and frontend for `multi-agent/`
2. Send a travel-planning prompt in the UI
3. Watch the task board and shared document update
4. Verify the facilitator performs a final merge/review pass after specialists finish
5. Confirm the final answer reflects the reviewed itinerary, not just the raw scratchpad contents

## Success Criteria

- [ ] The facilitator can access the consolidation and clean-review tools again
- [ ] The facilitator prompt includes an explicit merge/review phase
- [ ] Specialist agents still write their candidate content into the shared document
- [ ] The facilitator performs a final synthesis step before answering the user
- [ ] The final answer reflects a reviewed itinerary rather than raw scratchpad output

## Tips

- Keep the fix small and focused on facilitator behavior
- Do not add a new subsystem
- Do not rewrite the scratchpad classes
- If the document is being written correctly but never properly finalized, you are looking in the right place

If students get blocked, they can compare their work with:

- `solutions\06-agents-scratchpad\README.md`
