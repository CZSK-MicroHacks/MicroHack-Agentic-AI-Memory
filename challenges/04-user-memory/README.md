# Challenge 04 — User Memory

## Overview

Your chat agent works, conversations are saved, and memories are being built — but the agent treats every user the same. It doesn't know your name, your preferences, or anything about you personally. Even if you've told it your name five times across different conversations, it starts fresh every time.

In this challenge, you will implement **user profile memory** — the ability for the agent to **learn about the user** during conversation and **use that knowledge** to personalise future responses. After completing this challenge, the agent will automatically extract personal facts from conversations and inject them into its system prompt.

## What's Already in Place

- ✅ The `UserProfileMemoryStore` class in `user_profile_memory.py` is fully implemented (Cosmos DB CRUD)
- ✅ The profile REST API endpoints exist in `server.py` (`GET /profile`, `PUT /profile`, `DELETE /profile`, `POST /profile/generate`, `POST /profile/generate-all`)
- ✅ The `ProfileAgent` class in `profile_agent.py` can extract profile data from conversations (used by REST endpoints)
- ✅ The `update_user_profile` tool function is implemented in `agent_tools.py` — but it's **not registered** in the tool list
- ✅ The master prompt (`customer_support.j2`) already includes `{% include 'user_profile.j2' %}` and `{% include 'profile_update.j2' %}` — but those templates are empty
- ✅ The server already fetches the user profile before each chat turn and passes it to the template renderer

## Your Task

You need to implement three things:

### Part 1: Write the `profile_update.j2` prompt template

Open `backend/prompts/profile_update.j2`. This template is included in the master system prompt and tells the agent **when and how** to call the `update_user_profile` tool.

Your prompt should instruct the agent to:
- Watch for personal information the user reveals during conversation (name, location, job, interests, habits, preferences, current status, personal facts)
- Call `update_user_profile` only when the user **explicitly** states new or changed info
- Not infer or guess — only use clearly stated facts
- Not mention the update to the user (continue naturally)
- Pass only changed fields, not the entire profile
- For object fields (`basic_info`, `preferences`, `status`): pass a dict with only changed keys
- For array fields (`interests`, `habits`, `facts`): pass the full desired array (merge new items with existing ones)

> **💡 Tip:** Look at the `update_user_profile` tool signature in `agent_tools.py` to understand the available parameters. Ask GitHub Copilot: *"Write a system prompt section that instructs an AI agent to detect personal information in conversation and call the update_user_profile tool with the right parameters."*

### Part 2: Enable the `update_user_profile` tool

Open `backend/agent_tools.py` and find the `all` property and `for_rag_mode` method. The `update_user_profile` tool function is already implemented, but it's **not included** in the tool lists returned to the agent.

Add `self.update_user_profile` to both:
- The `all` property return list
- The `base` list in `for_rag_mode`

> **💡 Tip:** Look for the `TODO: Challenge 04` comments in the file.

### Part 3: Write the `user_profile.j2` prompt template

Open `backend/prompts/user_profile.j2`. This template is included in the master system prompt and **injects the user's stored profile** into the prompt so the agent can personalise responses.

The template receives a `user_profile` variable (a dict from Cosmos DB). Your template should:
- Only render when `user_profile` is defined and not empty (use Jinja2 `{%- if ... %}`)
- Include a header like `== USER PROFILE ==` with instructions for the agent to use the data naturally
- Conditionally render each profile section that has data:
  - `basic_info` (dict) — e.g., name, location, job
  - `interests` (list) — hobbies, topics
  - `habits` (list) — routines, patterns
  - `preferences` (dict) — communication style, shipping, etc.
  - `status` (dict) — current life events, mood
  - `facts` (list) — pets, allergies, family, birthday
- Instruct the agent to use the profile naturally — **not** repeat it back verbatim

> **💡 Tip:** Use Jinja2 filters like `tojson` for dicts and `join(", ")` for lists. Ask GitHub Copilot: *"Write a Jinja2 template that renders a user profile dict into a system prompt section with conditional rendering per field."*

#### Jinja2 Quick Reference

If you're new to Jinja2 templates, here's a quick primer. Jinja2 uses `{%` and `%}` for logic and `{{` and `}}` for outputting values:

```jinja2
{# This is a comment — not rendered #}

{# Conditional block — only renders if the variable is defined and truthy #}
{%- if my_variable is defined and my_variable %}
This text only appears when my_variable has a value.
{%- endif %}

{# Outputting a dict as JSON string #}
{{ some_dict | tojson }}
{# → {"name": "Alice", "location": "Prague"} #}

{# Joining a list into a comma-separated string #}
{{ some_list | join(", ") }}
{# → hiking, coffee, TypeScript #}

{# Nested conditionals — check a field inside the variable #}
{%- if user_profile.interests %}
Interests: {{ user_profile.interests | join(", ") }}
{%- endif %}
```

Here's a **starter example** — a template that conditionally renders just one section:

```jinja2
{%- if user_profile is defined and user_profile %}

== USER PROFILE ==
The following is known about the current user. Use it naturally.

{%- if user_profile.basic_info %}
Basic info: {{ user_profile.basic_info | tojson }}
{%- endif %}

{# TODO: Add more sections here (interests, habits, preferences, status, facts) #}

{%- endif %}
```

Use `{%- ... %}` (with the dash) instead of `{% ... %}` to strip whitespace before the tag — this keeps the rendered prompt clean without extra blank lines.

## Profile Document Schema

The profile stored in Cosmos DB has this structure (for reference when writing templates):

```json
{
  "id": "<user_id>",
  "user_id": "<user_id>",
  "version": 3,
  "basic_info": { "name": "Alice", "location": "Prague", "job": "Developer" },
  "interests": ["hiking", "coffee", "TypeScript"],
  "habits": ["morning jogger", "reads before bed"],
  "preferences": { "communication": "casual", "shipping": "express" },
  "status": { "current_project": "migrating to microservices" },
  "facts": ["has a golden retriever named Max", "allergic to peanuts"],
  "source_conversations": [...],
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-03-16T09:15:00Z"
}
```

## Environment Variables

These are already configured in `backend/.env`:

| Variable | Description |
|----------|-------------|
| `COSMOS_ENDPOINT` | Cosmos DB endpoint URL |
| `COSMOS_KEY` | Cosmos DB access key (empty = use AAD auth) |
| `COSMOS_UPM_DATABASE_NAME` | Database name (default: `userprofiles`) |
| `COSMOS_UPM_CONTAINER_NAME` | Container name (default: `userprofiles`) |

## Validation

After implementing all three parts:

1. **Restart the backend** (`uv run uvicorn server:app --reload`)
2. **Send a message** like *"Hi, my name is Alice and I live in Prague"*
3. **Check the profile panel** in the UI — your name and location should appear
4. **Start a new conversation** and send any message — the agent should greet you by name
5. **Verify in Azure Portal:**
   - Navigate to your Cosmos DB account
   - Open **Data Explorer**
   - Select the `userprofiles` database → `userprofiles` container
   - You should see a profile document with your user ID

## Success Criteria

- [ ] The agent detects personal information in conversation and calls `update_user_profile`
- [ ] Profile data is persisted to Cosmos DB via the tool
- [ ] The system prompt includes the user's profile when rendering `customer_support.j2`
- [ ] The agent uses profile data to personalise responses (e.g., greeting by name)
- [ ] The agent does NOT hallucinate or repeat profile data verbatim — it uses it naturally
- [ ] Profile updates work incrementally — new info is merged, not overwritten
