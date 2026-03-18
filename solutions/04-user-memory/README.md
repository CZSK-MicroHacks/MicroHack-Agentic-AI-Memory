# Solution 04 — User Memory

This solution implements user profile memory in three parts: a profile update prompt, tool registration, and a profile injection template.

## Part 1: `profile_update.j2` prompt template

Replace the contents of `backend/prompts/profile_update.j2` with:

```jinja2
== PROFILE UPDATE ==
You have access to an update_user_profile tool. As you converse, watch for
any NEW personal information the user reveals:
- Name, location, job, company
- Hobbies, interests, topics they care about
- Behavioral habits or routines
- Preferences (communication, shipping, contact method, etc.)
- Current status or life events
- Personal facts (pets, allergies, family, birthday, etc.)

Rules for calling update_user_profile:
- ONLY call when the user EXPLICITLY states new or changed personal info.
- Do NOT call for information already in the profile above.
- Do NOT infer or guess — only use clearly stated facts.
- Do NOT mention the update to the user. Continue naturally.
- Most messages will NOT warrant a call.
- Make ONE single call per turn with ALL new info combined in one patch.
  Never split updates into multiple parallel calls.

Pass only the parameters that changed — omit unchanged ones:
- For objects (basic_info, preferences, status): pass a dict with only changed keys.
- For arrays (interests, habits, facts): pass the FULL desired array
  (merge new items with existing ones yourself).

Example — user says "I just moved to Portland and I love sushi":
  → basic_info={"location": "Portland, OR"}, interests=["<existing>", "sushi"]
```

## Part 2: Enable the `update_user_profile` tool

In `backend/agent_tools.py`, add `self.update_user_profile` to both the `all` property and the `for_rag_mode` method:

```python
@property
def all(self) -> list:
    """All tools including agentic RAG via MCP.

    TODO: Challenge 05 — Add self._rag_mcp_tool to this list to enable
    knowledge base search via MCP.
    """
    return [self.get_order_status, self.check_memory, self.update_user_profile]

def for_rag_mode(self, rag_mode: str) -> list:
    """Return tool list for the given RAG mode.

    TODO: Challenge 05 — Implement RAG mode switching:
      - "agentic" → base tools + self._rag_mcp_tool
      - "classic" → base tools + self.do_classic_rag
      - "none"    → base tools only
    """
    base = [self.get_order_status, self.check_memory, self.update_user_profile]
    # TODO: Add RAG tools based on rag_mode
    return base
```

## Part 3: `user_profile.j2` prompt template

Replace the contents of `backend/prompts/user_profile.j2` with:

```jinja2
{%- if user_profile is defined and user_profile %}

== USER PROFILE ==
You have access to the following personal information about the current user.
Use it to personalise your responses — greet them by name when appropriate,
respect their stated preferences, and reference their interests or habits
when relevant. Do NOT repeat the profile back verbatim; use it naturally.

{%- if user_profile.basic_info %}
Basic info: {{ user_profile.basic_info | tojson }}
{%- endif %}
{%- if user_profile.interests %}
Interests: {{ user_profile.interests | join(", ") }}
{%- endif %}
{%- if user_profile.habits %}
Habits: {{ user_profile.habits | join(", ") }}
{%- endif %}
{%- if user_profile.preferences %}
Preferences: {{ user_profile.preferences | tojson }}
{%- endif %}
{%- if user_profile.status %}
Current status: {{ user_profile.status | tojson }}
{%- endif %}
{%- if user_profile.facts %}
Other facts: {{ user_profile.facts | join("; ") }}
{%- endif %}
{%- endif %}
```

## Key Concepts

- **Prompt-based profile injection:** The user profile is rendered into the system prompt via Jinja2 templates. The agent "sees" the profile as part of its instructions — no special API or memory layer needed.
- **Tool-based profile updates:** The agent calls `update_user_profile` as a tool during conversation. This keeps the update logic in the agent's reasoning loop rather than in post-processing.
- **Merge semantics:** Object fields (dicts) use JSON merge patch — only changed keys are sent. Array fields (lists) require the full desired list to avoid partial overwrites.
- **Silent updates:** The agent is instructed to never mention profile updates to the user. This creates a natural experience where the agent "just remembers" things.
- **Conservative extraction:** The prompt emphasises explicit statements only — no inference or guessing — to avoid polluting the profile with incorrect assumptions.
