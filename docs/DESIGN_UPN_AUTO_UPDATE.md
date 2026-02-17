# Continuous User Profile Memory (UPM) Update — Feature Design

> **Status**: Implemented & Deployed (2026-02-17)
>
> This document reflects the **final shipped implementation**, updated after
> iterative development and live debugging.

## 1. Overview

User Profile Memory (UPM) was previously updated only via **manual triggers** — the user clicks "Generate Profile" or "Update Profile" in the sidebar, which POST to `/profile/generate` or `/profile/generate-all`. The profile agent is a separate `ChatAgent` that runs outside of the conversation flow.

This feature adds **continuous, inline UPM updates** driven by the main conversation agent itself. The LLM evaluates every user message for notable personal information and, when warranted, calls a new `update_user_profile` tool that applies the changes to Cosmos DB. The frontend profile drawer also refreshes automatically when opened.

**Key improvements:**

| Aspect | Previous (Manual) | New (Continuous) |
|--------|-------------------|------------------|
| Trigger | User clicks a button | LLM decides autonomously per-message |
| Agent | Separate `ProfileAgent` ChatAgent | Main `CustomerSupportAgent` via tool call |
| Update format | Full profile JSON replacement | RFC 7396 JSON Merge Patch (partial) |
| Risk of malformed JSON | High — LLM must produce entire profile | Low — LLM only produces the delta |
| Maintenance | User must remember to update | Automatic, zero-effort |
| Frontend freshness | Profile loaded once at login | Re-fetched every time profile drawer is opened |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    CustomerSupportAgent                           │
│    (Master Prompt — customer_support.j2)                         │
│                                                                   │
│    Tools:                                                         │
│    ├── get_order_status(order_id)                                │
│    ├── check_memory(query)                                       │
│    ├── do_rag(query)                                             │
│    └── update_user_profile(                                      │
│            basic_info?, interests?, habits?,                      │
│            preferences?, status?, facts?                         │
│        )                              ◄── NEW                    │
│                                                                   │
│    System Prompt now includes:                                   │
│    • Existing user profile (read-only context, already there)    │
│    • NEW: Instructions to detect notable personal info           │
│    • NEW: Instructions to call update_user_profile               │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       │  LLM decides: "user mentioned they moved
                       │  to Portland" → tool call
                       │
                       ▼
         ┌─────────────────────────────┐
         │   update_user_profile tool  │
         │                             │
         │  Input: typed parameters    │
         │    basic_info={             │
         │      "location": "Portland" │
         │    }                        │
         │                             │
         │  Logic:                     │
         │  1. Build patch from args   │
         │  2. Read current UPM doc    │
         │  3. Apply RFC 7396 merge    │
         │  4. Upsert to Cosmos DB     │
         │  5. Return change summary   │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │   Cosmos DB                 │
         │   userprofiles container    │
         │                             │
         │   Document: user-alice      │
         │   (patched in-place)        │
         └─────────────────────────────┘
```

**No separate agent.** The main `CustomerSupportAgent` gains awareness of profile updates through its system prompt and can trigger them via the new tool. The existing `ProfileAgent` class and its `/profile/generate`, `/profile/generate-all` endpoints remain available as a manual fallback but are no longer the primary update path.

---

## 3. Master Prompt Changes (`customer_support.j2`)

### 3.1 New Section: Profile Update Instructions

A new `== PROFILE UPDATE ==` section is appended **after** the existing
`== USER PROFILE ==` block.  It renders **unconditionally** (not gated on
`user_profile` existing) so the LLM can create a profile from scratch if the
user reveals personal info for the first time.

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

### 3.2 Template Structure (Final)

```
1. Core customer support instructions          (existing)
2. Tool descriptions (get_order_status, etc.)  (existing)
3. Citation / annotation rules                 (existing)
4. == USER PROFILE == (read-only context)      (existing, gated on user_profile)
5. == PROFILE UPDATE ==                        (NEW — always rendered)
```

### 3.3 Key Prompt Design Decisions

- **"ONE single call per turn"** rule was added after observing gpt-4o-mini
  generate parallel `update_user_profile` calls that caused Cosmos DB race
  conditions (later call overwrites earlier call's write).
- **Parameter-style examples** (`basic_info={...}, interests=[...]`) instead
  of JSON object examples — matches the multi-parameter tool signature so the
  LLM knows to pass named arguments, not a single JSON blob.

---

## 4. New Tool: `update_user_profile`

### 4.1 Tool Signature (Final — Multi-Parameter)

```python
@tool
async def update_user_profile(
    basic_info: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with keys like name, location, job, company. Only include changed fields.",
    )] = None,
    interests: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of user interests (merge new items with existing ones).",
    )] = None,
    habits: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of user habits (merge new items with existing ones).",
    )] = None,
    preferences: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with user preferences. Only include changed fields.",
    )] = None,
    status: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with current life status or events. Only include changed fields.",
    )] = None,
    facts: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of personal facts (pets, allergies, family, birthday, etc.).",
    )] = None,
) -> str:
```

### 4.2 Why Multi-Parameter (Not a Single `patch: str`)

The original design used a single `patch: str` parameter with a JSON
description. This was changed during implementation for the following
reasons:

| Approach | Problem |
|----------|---------|
| `patch: str` (JSON string) | The Microsoft Agent Framework's `@tool` decorator parses the LLM's function-call arguments via Pydantic. The LLM sends arguments as a **native JSON object**, e.g. `{"basic_info": {"name": "X"}}`. Pydantic then looks for a field called `patch` — but the LLM omits the wrapper key and sends top-level profile keys directly. This caused `ValidationError: patch — Field required`. |
| `patch: dict[str, Any]` (dict) | Same problem — the LLM sends `{"basic_info": {...}, "interests": [...]}` as top-level keys, not `{"patch": {"basic_info": {...}}}`. |
| **Individual parameters** (final) | Each profile key becomes a named optional parameter. The LLM's output `{"basic_info": {...}, "interests": [...]}` maps directly to function arguments. Pydantic validates each parameter independently. |

**Lesson learned**: When using function-calling with the Microsoft Agent
Framework, the LLM's JSON output keys must match the function parameter names
exactly. A single wrapper parameter forces the LLM to nest its output, which
it frequently fails to do.

### 4.3 Tool Implementation Logic

```
update_user_profile(basic_info?, interests?, habits?, preferences?, status?, facts?) -> str:
    │
    ├── 1. Build patch dict from non-None arguments
    │       patch_dict = {k: v for k, v in args if v is not None}
    │
    ├── 2. Early return if patch is empty
    │       → "No profile fields provided"
    │
    ├── 3. Read current profile from Cosmos DB
    │       user_id = _current_user_id.get()
    │       existing = await profile_store.get_profile(user_id)
    │
    ├── 4. Apply RFC 7396 merge
    │       merged = json_merge_patch(existing_sections, patch_dict)
    │       (see §4.4 for merge algorithm)
    │
    ├── 5. Upsert to Cosmos DB
    │       await profile_store.upsert_profile(user_id, merged, source_conversation=None)
    │
    └── 6. Return summary string
            e.g. "Profile updated: basic_info, interests"
```

### 4.4 RFC 7396 JSON Merge Patch Algorithm

The `json_merge_patch` function is a pure recursive merge. Key-filtering is
**not** done inside this function — callers are responsible for pre-filtering
(the tool signature already enforces valid keys via typed parameters).

```python
def json_merge_patch(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7396 JSON Merge Patch — recursive merge with null-removal."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = json_merge_patch(result[key], value)
        else:
            result[key] = value
    return result
```

> **Design note**: An earlier version included an `_ALLOWED_PROFILE_KEYS`
> allowlist check inside `json_merge_patch`. This was removed because it
> blocked nested sub-keys (e.g. `location` inside `basic_info` was rejected
> by the allowlist). Since the multi-parameter tool signature already
> constrains input to the six allowed profile sections, the inner filter was
> both redundant and harmful.

**Behavior for arrays** (`interests`, `habits`, `facts`): Per RFC 7396, arrays are **replaced entirely** (not merged element-by-element). The prompt instructs the LLM to pass the full desired array, having merged new items with existing ones from the profile context visible in the system prompt.

**Example:**

Current profile:
```json
{
  "basic_info": { "name": "Alice", "location": "Seattle" },
  "interests": ["hiking", "cooking"]
}
```

LLM tool call:
```
update_user_profile(
    basic_info={"location": "Portland, OR"},
    interests=["hiking", "cooking", "bouldering"]
)
```

Result after merge:
```json
{
  "basic_info": { "name": "Alice", "location": "Portland, OR" },
  "interests": ["hiking", "cooking", "bouldering"]
}
```

`basic_info.name` is preserved (not in patch). `location` is updated. `interests` is replaced with the new full array.

### 4.5 Validation & Safety

| Risk | Mitigation |
|------|-----------|
| Invalid argument types from LLM | Pydantic validates each parameter's type at the framework level before our code runs |
| Unknown keys | Impossible — only the six named parameters are accepted |
| Empty call (all params None) | Returns "No profile fields provided" |
| Concurrent writes | Cosmos DB `upsert_item` is last-writer-wins; acceptable for single-user single-session |
| Parallel tool calls (race condition) | Prompt instructs "ONE single call per turn"; framework processes sequentially within a turn |

---

## 5. Tool Registration

### 5.1 Adding to Agent Tools List

```python
# Default agent — includes update_user_profile
agent = ChatAgent(
    name="CustomerSupportAgent",
    instructions=CUSTOMER_SUPPORT_PROMPT,
    chat_client=chat_client,
    tools=[get_order_status, check_memory, do_rag, update_user_profile],
)

# Personalized agent builder — includes update_user_profile
def _build_personalized_agent(user_profile, *, rag_enabled=True) -> ChatAgent:
    tools = [get_order_status, check_memory, update_user_profile]
    if rag_enabled:
        tools.append(do_rag)
    ...
```

---

## 6. Changes Summary

### 6.1 Modified Files

| File | Change | Description |
|------|--------|-------------|
| [backend/prompts/customer_support.j2](../backend/prompts/customer_support.j2) | **Modify** | Add `== PROFILE UPDATE ==` section (~25 lines) |
| [backend/server.py](../backend/server.py) | **Modify** | Add `json_merge_patch()` helper, `update_user_profile` tool (multi-parameter), register tool in agent tool lists |
| [frontend/src/app.ts](../frontend/src/app.ts) | **Modify** | `toggleProfileDrawer()` calls `fetchProfile()` when opening |
| [backend/user_profile_memory.py](../backend/user_profile_memory.py) | **No change** | Existing `upsert_profile` and `get_profile` already support the needed operations |
| [backend/profile_agent.py](../backend/profile_agent.py) | **No change** | Remains as manual fallback; not modified |

### 6.2 No New Files

All changes fit within existing modules. No new Python files, no new dependencies, no new database migrations.

### 6.3 No New API Endpoints

The profile update happens **inside the chat flow** via the tool call. Existing REST endpoints (`GET /profile`, `PUT /profile`, `DELETE /profile`, `POST /profile/generate`, `POST /profile/generate-all`) remain unchanged.

---

## 7. Detailed Change: `server.py`

### 7.1 Helper Function: `json_merge_patch`

Located after the `_current_user_id` ContextVar definition:

```python
def json_merge_patch(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7396 JSON Merge Patch — recursive merge with null-removal."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = json_merge_patch(result[key], value)
        else:
            result[key] = value
    return result
```

### 7.2 Tool Function: `update_user_profile`

See §4.1 for the full signature.  Key implementation details:

```python
@tool
async def update_user_profile(
    basic_info=None, interests=None, habits=None,
    preferences=None, status=None, facts=None,
) -> str:
    user_id = _current_user_id.get()

    # Build patch from non-None arguments
    patch_dict: dict[str, Any] = {}
    if basic_info is not None:
        patch_dict["basic_info"] = basic_info
    if interests is not None:
        patch_dict["interests"] = interests
    # ... same for habits, preferences, status, facts

    if not patch_dict:
        return "No profile fields provided"

    # Read → merge → upsert
    existing = await profile_store.get_profile(user_id)
    existing_sections = {"basic_info": {}, "interests": [], ...}
    if existing:
        for key in existing_sections:
            if key in existing:
                existing_sections[key] = existing[key]

    merged = json_merge_patch(existing_sections, patch_dict)

    await profile_store.upsert_profile(
        user_id=user_id,
        profile_sections=merged,
        source_conversation=None,
    )

    changed_keys = list(patch_dict.keys())
    return f"Profile updated: {', '.join(changed_keys)}"
```

---

## 8. Detailed Change: `customer_support.j2`

### 8.1 New Section (appended after the existing `USER PROFILE` block)

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

---

### 8.2 Detailed Change: `frontend/src/app.ts`

The profile drawer toggle now re-fetches the profile from the backend
every time it is opened, so changes made by the `update_user_profile` tool
during a chat session are immediately visible:

```typescript
private toggleProfileDrawer() {
    this.profileDrawerOpen = !this.profileDrawerOpen;
    if (this.profileDrawerOpen) {
        this.fetchProfile();
    }
}
```

Previously, `toggleProfileDrawer()` only flipped the `profileDrawerOpen`
boolean. The profile data was only fetched once at app startup and after
manual "Generate Profile" actions.

---

## 9. Data Flow

### 9.1 Continuous Update Flow (Happy Path)

```
User: "By the way, I just got a new dog named Rex"
    │
    ▼
CustomerSupportAgent receives message
    │
    ├─ LLM evaluates: user revealed a new personal fact
    │   (not in current profile context)
    │
    ├─ LLM generates response text: "That's great! Rex sounds like a fun name.
    │   How can I help you today?"
    │
    ├─ LLM also generates tool call:
    │   update_user_profile(
    │     facts=["Has two cats named Luna and Milo", "Has a dog named Rex"]
    │   )
    │
    ▼
update_user_profile tool executes:
    ├─ 1. Build patch_dict from non-None params: {"facts": [...]}
    ├─ 2. Read existing profile from Cosmos DB
    ├─ 3. Merge: facts array replaced with new array
    ├─ 4. Upsert merged profile to Cosmos DB
    └─ 5. Return "Profile updated: facts"
    │
    ▼
Agent stream continues → user sees response
(tool call result is consumed internally, not shown to user)
```

### 9.2 No-Update Path (Most Messages)

```
User: "What's the status of ORD-001?"
    │
    ▼
CustomerSupportAgent receives message
    │
    ├─ LLM evaluates: no personal info → does NOT call update_user_profile
    ├─ LLM calls get_order_status("ORD-001") instead
    └─ Normal response flow
```

### 9.3 First-Time Profile Creation

```
User: "Hi, I'm Alice from Seattle. I'm a software engineer."
    │
    ▼
CustomerSupportAgent (no existing profile in context)
    │
    ├─ LLM detects: name, location, occupation — all new
    ├─ LLM calls update_user_profile(
    │     basic_info={
    │       "name": "Alice",
    │       "location": "Seattle",
    │       "occupation": "Software Engineer"
    │     }
    │   )
    │
    ▼
update_user_profile tool:
    ├─ Build patch_dict: {"basic_info": {...}}
    ├─ Read profile → None (doesn't exist yet)
    ├─ Merge with empty skeleton → creates initial profile
    └─ Upsert → new document in Cosmos DB (version=1)
```

---

## 10. Edge Cases & Design Decisions

### 10.1 Array Handling Strategy

**Problem**: RFC 7396 replaces arrays wholesale. The LLM must produce the full desired array, not just new items.

**Solution**: The LLM has access to the current profile in its system prompt context (the `== USER PROFILE ==` section). The prompt explicitly instructs it to merge new items with existing ones before calling the tool.

**Risk**: The LLM might accidentally drop existing array items. This is mitigated by:
- Clear prompt instructions emphasizing "merge new items with existing ones"
- The existing profile being visible in context
- Conservative model behavior (GPT-4o-mini typically preserves listed items)

**Acceptable trade-off**: Occasionally losing an array item is better than the previous approach where the LLM must produce the entire profile JSON from scratch every time.

### 10.2 Concurrency

If two chat sessions for the same user both trigger `update_user_profile` simultaneously, Cosmos DB `upsert_item` uses last-writer-wins. This is acceptable because:
- Single-user concurrent sessions are rare
- Profile updates are additive and non-critical
- The worst case is losing one update, which will be re-detected in the next conversation

The prompt's "ONE single call per turn" rule also prevents race conditions within a single turn (multiple parallel tool calls writing to the same profile).

### 10.3 Tool Call Visibility

The `update_user_profile` tool call appears in the AG-UI event stream as `TOOL_CALL_START`/`TOOL_CALL_END` events. The frontend displays a brief "[Calling tool: update_user_profile]" indicator. This is acceptable and even desirable for transparency. If hiding is preferred in the future, the frontend can filter by tool name.

### 10.4 Profile Freshness

Two mechanisms ensure users see up-to-date profiles:

1. **System prompt**: The user profile is loaded at the **start of each `/chat` request** (via `_build_personalized_agent`). If `update_user_profile` is called mid-conversation, the system prompt still contains the **old** profile. This is fine because the LLM just processed the user's message that triggered the update — it knows the new info. The next `/chat` request will rebuild the agent with the updated profile.

2. **Frontend drawer**: `toggleProfileDrawer()` calls `fetchProfile()` each time the drawer opens, so the user always sees the latest Cosmos DB state — including any updates made by the tool during the current chat session.

### 10.5 Relationship to Existing Manual Endpoints

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `POST /profile/generate` | **Kept** | Manual one-conversation profile extraction (fallback) |
| `POST /profile/generate-all` | **Kept** | Manual bulk profile generation (initial setup) |
| `PUT /profile` | **Kept** | Manual profile editing |
| `GET /profile` | **Kept** | Read profile for frontend display |
| `DELETE /profile` | **Kept** | Delete profile |
| `update_user_profile` tool | **Added** | Inline auto-update during conversation |

The manual endpoints remain useful for:
- Initial bulk profile generation from historical conversations
- Manual corrections when the auto-update misses or misinterprets something
- Frontend profile editing UI

---

## 11. File Changes Summary

| File | Change Type | Lines (est.) | Description |
|------|-------------|-------------|-------------|
| `backend/prompts/customer_support.j2` | **Modify** | +25 | Add `== PROFILE UPDATE ==` instructions section |
| `backend/server.py` | **Modify** | +70 | Add `json_merge_patch()` helper, `update_user_profile` tool (6 params), update tool registrations |
| `frontend/src/app.ts` | **Modify** | +3 | `toggleProfileDrawer()` calls `fetchProfile()` on open |
| `backend/user_profile_memory.py` | None | 0 | No changes needed |
| `backend/profile_agent.py` | None | 0 | No changes needed |

**Total**: ~100 lines of new/modified code across 3 files.

**No new files. No new dependencies. No new API endpoints. No database changes.**

---

## 12. Testing Strategy

### 12.1 Unit Tests

- `json_merge_patch()`:
  - Scalar field update
  - Nested dict merge (only changed keys)
  - Array full replacement
  - Null value removes key
  - Empty patch returns target unchanged
  - Sub-keys like `location` inside `basic_info` are NOT filtered

- `update_user_profile()`:
  - Valid params → profile updated in store
  - All params None → returns "No profile fields provided"
  - First-time profile creation (no existing doc)
  - Incremental update preserves unmentioned keys

### 12.2 Integration Tests

- Send a chat message containing personal info → verify `update_user_profile` tool call appears in the AG-UI stream → verify profile document updated in Cosmos DB
- Send a routine question → verify NO tool call to `update_user_profile`
- Send info that's already in the profile → verify no duplicate update
- Open profile drawer after chat → verify drawer shows updated data

### 12.3 Manual Verification (Performed)

Testing was done locally with `AUTH_MODE=mock` and the `X-Mock-User-ID` header:

| User | Scenario | Result |
|------|----------|--------|
| `user-alice` | Existing profile, incremental updates (name, location, then interests) | Profile version advanced 5→8; all fields preserved |
| `user-bob` | No existing profile, reveal name + location + interests in first message | Profile created from scratch (version 1) |
| `user-charlie` | Name with quotes ("Imperor X"), location, job | Profile created successfully (version 1); argument parsing worked |

---

## 13. Implementation Lessons Learned

### 13.1 Microsoft Agent Framework Argument Parsing

**Bug**: Using a single `patch: str` parameter caused `ValidationError: patch — Field required`. The framework's `@tool` decorator uses Pydantic to validate the LLM's function-call JSON arguments. The LLM sends `{"basic_info": {...}, "interests": [...]}` as **top-level keys** — it does not wrap them in `{"patch": "..."}`.

**Fix**: Changed to 6 individually typed optional parameters that match the LLM's output keys directly.

**Takeaway**: With the Microsoft Agent Framework's `@tool`, every function parameter name becomes a top-level key in the LLM's JSON function-call output. Design tool signatures so that parameter names match the keys the LLM will naturally produce.

### 13.2 Recursive Key Filtering Bug

**Bug**: An `_ALLOWED_PROFILE_KEYS` allowlist check inside `json_merge_patch()` blocked nested sub-keys (e.g. `location` inside `basic_info`) because `location` was not in the top-level allowlist.

**Fix**: Removed the allowlist check from the merge function entirely. The typed tool parameters already constrain input to the six allowed sections.

### 13.3 Parallel Tool Calls Race Condition

**Bug**: gpt-4o-mini sometimes issued multiple parallel `update_user_profile` calls for different profile sections. The second call's read-before-write executed before the first call's write completed, causing the second upsert to overwrite the first.

**Fix**: Added a prompt rule: "Make ONE single call per turn with ALL new info combined." This is sufficient because the framework processes tool calls sequentially within a turn, but the LLM must be told to combine them.

### 13.4 Malformed JSON from LLM

**Bug**: The LLM occasionally appended extra trailing braces to JSON payloads.

**Fix**: This was resolved naturally when switching from a JSON-string `patch` parameter to typed parameters — the framework's Pydantic parsing handles individual parameter types robustly.

---

## 14. Open Questions / Future Considerations

1. **Rate limiting**: The LLM might over-call the tool in long conversations. A future guard could throttle to max 1 profile update per N messages or per turn. For MVP, prompt instructions suffice.

2. **Audit trail**: The current implementation does not record which conversation triggered the auto-update (since `source_conversation` is `None` for tool-initiated updates). A future enhancement could pass the current session ID.

3. **User consent/notification**: Currently the update is silent. A future version could add a subtle UI indicator ("Profile updated") or a settings toggle to enable/disable auto-updates.

4. **Profile drift**: Over many conversations, the profile might accumulate stale information. Periodic review or a "Profile Health" feature could flag entries that haven't been referenced in N conversations.

5. **Model cost**: Each user message now potentially triggers an extra tool call (though most won't). The cost delta is minimal since the LLM already processes the message — it's just adding a function call to its output, not an extra API request.
