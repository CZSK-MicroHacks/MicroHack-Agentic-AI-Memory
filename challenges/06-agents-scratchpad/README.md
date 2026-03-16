# Challenge 06: Agents Scratchpad

This challenge uses the travel-planner demo in `multi-agent/` to teach one core idea:

> Shared memory is only useful when agents both write into it and a coordinator comes back to reconcile the result.

## Where to work

- The runnable app lives in `multi-agent/`.
- The **student version** of the app lives on the `student-tk` branch.
- The `main` branch keeps the completed reference implementation.

## What students should notice

In the student branch, the workflow looks partially correct:

- the facilitator creates tasks
- specialist agents run
- the shared document fills with candidate entries
- the UI shows agent activity and scratchpad updates

But the facilitator stops before the merge/review phase, so the shared scratchpad never becomes a properly reviewed final itinerary.

## Learning goal

Understand the difference between:

- agents writing intermediate ideas into a shared scratchpad
- a facilitator consolidating those ideas into a final version

That is the main message of this challenge.

## Student task

Restore the facilitator's final merge/review behavior with a **small mixed change**:

1. Fix the facilitator-side tool wiring in `multi-agent\backend\tools.py`.
2. Fix the facilitator instructions in `multi-agent\backend\prompts\facilitator.j2`.

## Expected outcome after the fix

After all specialist tasks are complete, the facilitator should:

1. review the shared document
2. consolidate entries where needed
3. read the clean version of the document
4. only then produce the final answer

## Files to inspect

- `multi-agent\backend\tools.py`
- `multi-agent\backend\prompts\facilitator.j2`
- optionally `multi-agent\README.md` for the intended architecture

## Hints

- Do not add a new subsystem.
- Do not rewrite the scratchpad classes.
- Keep the fix small and focused on facilitator behavior.
- If the document can be written but not properly finalized, you are looking in the right place.

## If students get stuck

They can compare their work against the guide in:

- `solutions\06-agents-scratchpad\README.md`
