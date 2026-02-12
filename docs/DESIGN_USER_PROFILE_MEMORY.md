# User Profile Memory (UPM) — Feature Design

## 1. Overview

User Profile Memory (UPM) builds a **persistent, evolving profile** for each user by extracting personal facts — interests, habits, basic information, status, preferences — from their conversations. Unlike Conversation Memory (which summarizes individual conversations), UPM maintains a **single living document per user** that grows and evolves over time.

**Key principles:**
- **One profile per user** — stored as a single Cosmos DB document.
- **Opt-in** — users trigger profile generation/update manually via a button.
- **Additive & corrective** — the profile agent merges new facts into the existing profile, updates changed facts, and can remove outdated ones.
- **Non-destructive** — if a conversation contains no interesting personal info, the profile remains unchanged.

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  Conversation History       │         │   User Profile Memory        │
│  (Cosmos DB)                │  ────►  │   (Cosmos DB)                │
│                             │  agent  │                              │
│  • id (session_id)          │ extract │  • id (= user_id)            │
│  • user_id                  │         │  • user_id (partition key)    │
│  • messages[]               │         │  • basic_info {}             │
│  • ...                      │         │  • interests []              │
│                             │         │  • habits []                 │
│                             │         │  • preferences {}            │
│                             │         │  • status {}                 │
│                             │         │  • facts []                  │
│                             │         │  • source_conversations []   │
│                             │         │  • created_at                │
│                             │         │  • updated_at                │
└─────────────────────────────┘         └──────────────────────────────┘
     N conversations                          1 profile per user
```

---

## 2. Data Model

### 2.1 Profile Document Schema

Stored in Cosmos DB, database `userprofiles`, container `userprofiles`, partitioned by `user_id`.

```json
{
  "id": "user-alice",
  "user_id": "user-alice",
  "version": 3,
  "basic_info": {
    "name": "Alice Johnson",
    "location": "Seattle, WA",
    "occupation": "Software Engineer",
    "company": "Contoso",
    "timezone": "PST"
  },
  "interests": [
    "hiking",
    "machine learning",
    "cooking Italian food"
  ],
  "habits": [
    "orders coffee beans monthly",
    "prefers express shipping"
  ],
  "preferences": {
    "communication_style": "concise and technical",
    "shipping_preference": "express",
    "contact_preference": "email"
  },
  "status": {
    "current_mood": null,
    "recent_issues": "waiting for replacement of order ORD-003",
    "loyalty_tier": null
  },
  "facts": [
    "Has two cats named Luna and Milo",
    "Allergic to peanuts",
    "Birthday is in March"
  ],
  "source_conversations": [
    {
      "conversation_id": "conv-abc-123",
      "extracted_at": "2026-02-10T12:00:00Z",
      "facts_added": 3,
      "facts_updated": 1,
      "facts_removed": 0
    }
  ],
  "created_at": "2026-02-08T10:00:00Z",
  "updated_at": "2026-02-10T12:00:00Z"
}
```

**Design decisions:**

| Field | Type | Purpose |
|-------|------|---------|
| `id` / `user_id` | string | Primary key = user ID; one doc per user; partition key = `user_id` |
| `version` | int | Monotonically incrementing counter, bumped on every update |
| `basic_info` | object | Structured personal information (name, location, job, etc.) |
| `interests` | string[] | Hobbies, topics, areas of interest |
| `habits` | string[] | Behavioral patterns observed across conversations |
| `preferences` | object | Expressed preferences (communication, shipping, etc.) |
| `status` | object | Transient/temporal state (mood, recent issues, etc.) |
| `facts` | string[] | Miscellaneous personal facts that don't fit other categories |
| `source_conversations` | object[] | Audit trail — which conversations contributed to this profile |
| `created_at` / `updated_at` | ISO string | Timestamps |

### 2.2 Why Cosmos DB (Not PostgreSQL)

- The profile is a **flexible JSON document** — fields are added/removed/restructured over time. Cosmos DB's schemaless nature is ideal.
- **One document per user** with `user_id` as partition key gives guaranteed single-partition point reads (~1 RU).
- Aligns with the existing Cosmos DB setup used for Conversation History — reuses the same emulator/connection.
- No vector search needed for profiles — simple CRUD only.

### 2.3 Cosmos DB Configuration

| Setting | Value |
|---------|-------|
| Database name | `userprofiles` |
| Container name | `userprofiles` |
| Partition key | `/user_id` |
| Env vars | `COSMOS_UPM_DATABASE_NAME` (default: `userprofiles`), `COSMOS_UPM_CONTAINER_NAME` (default: `userprofiles`) |

Uses the same `COSMOS_ENDPOINT` and `COSMOS_KEY` as Conversation History.

---

## 3. Profile Agent

### 3.1 Architecture

The Profile Agent is a Microsoft Agent Framework `ChatAgent` that:
1. Receives the **existing profile** (or empty `{}` for first-time creation) and the **conversation messages**.
2. Analyzes the conversation for personal facts about the user.
3. Returns a **complete updated profile JSON** with merged/added/changed/removed information.

```
                 ┌──────────────────────────────────────┐
                 │           Profile Agent               │
                 │    (ChatAgent, Agent Framework)        │
                 │                                       │
   Input:        │  ┌─────────────────────────────────┐  │  Output:
   • existing    │  │  PROFILE_EXTRACTION_PROMPT       │  │  • updated
     profile     │  │                                  │  │    profile JSON
   • conversation│  │  Instructions for:               │  │  • change
     messages    │  │  - Extracting personal facts     │  │    summary
                 │  │  - Merging with existing profile │  │
                 │  │  - Handling conflicts/updates    │  │
                 │  │  - Deciding "no changes"         │  │
                 │  └─────────────────────────────────┘  │
                 └──────────────────────────────────────┘
```

### 3.2 Profile Extraction Prompt

```
You are a User Profile Memory agent. Your job is to analyze a conversation
and extract or update personal information about the user.

You receive:
1. The user's EXISTING profile (JSON) — may be empty for first-time creation.
2. A CONVERSATION TRANSCRIPT between the user and an assistant.

Your task:
- Identify any personal facts about the USER (not the assistant) mentioned
  in the conversation: name, location, job, interests, habits, preferences,
  current status, or any other notable personal information.
- Merge newly discovered facts into the existing profile:
  • ADD new facts that weren't in the profile before.
  • UPDATE facts that have changed (e.g., user moved to a new city).
  • REMOVE facts that the user explicitly contradicts or says are no longer true.
  • LEAVE UNCHANGED any existing facts not mentioned in this conversation.
- For the `status` section, update transient state (current issues, mood, etc.)
  based on the most recent information.

Output format — respond with ONLY a JSON object:
{
  "profile_changed": true | false,
  "change_summary": "Brief description of what changed, or 'No new personal information found'",
  "profile": {
    "basic_info": { ... },
    "interests": [ ... ],
    "habits": [ ... ],
    "preferences": { ... },
    "status": { ... },
    "facts": [ ... ]
  }
}

Rules:
- Output ONLY valid JSON, no markdown, no commentary.
- If the conversation contains NO personal information about the user,
  set "profile_changed": false and return the existing profile unchanged.
- Be conservative — only extract facts clearly stated by or about the user.
- Do NOT infer or guess information not explicitly mentioned.
- Do NOT include information about the assistant or the system.
- Keep string values concise (under 100 characters each).
- Keep arrays to a reasonable size (max ~20 items per category).
- Deduplicate — don't add facts that are already captured.
```

### 3.3 Agent Flow

```python
class ProfileAgent:
    """Extracts and updates user profile from conversation content."""

    async def extract_profile(
        self,
        existing_profile: dict | None,
        conversation_messages: list[dict],
        conversation_id: str,
    ) -> ProfileExtractionResult:
        """
        1. Format existing profile + conversation into prompt
        2. Run the profile extraction agent
        3. Parse response JSON
        4. Return ProfileExtractionResult(changed, summary, profile)
        """
```

**Key behavior:**
- If `profile_changed` is `false`, the store is NOT written to — avoiding unnecessary Cosmos DB writes.
- The `source_conversations` audit trail is managed by the store, not the agent.
- The `version` counter is bumped by the store on every successful update.

### 3.4 Input Construction

The agent input is structured as:

```
EXISTING PROFILE:
{existing_profile_json}

CONVERSATION:
user: Hi, I just moved to Portland from Seattle.
assistant: Welcome to Portland! How can I help you today?
user: I need to update my shipping address for my monthly coffee subscription.
...
```

---

## 4. Backend Architecture

### 4.1 New Module: `backend/user_profile_memory.py`

```
class UserProfileMemoryStore:
    """Async CRUD for user profiles stored in Cosmos DB."""

    def __init__(
        self,
        endpoint, key,
        database_name="userprofiles",
        container_name="userprofiles",
    )

    async def initialize() -> None
        # Create database and container if not exists
        # Partition key: /user_id

    async def close() -> None

    async def get_profile(user_id: str) -> dict | None
        # Point read by id=user_id, partition_key=user_id
        # Returns full profile document or None

    async def upsert_profile(user_id: str, profile: dict) -> dict
        # Upsert the profile document
        # Bumps version, updates updated_at
        # Appends to source_conversations if conversation_id provided

    async def delete_profile(user_id: str) -> bool
        # Hard-delete the profile document

    async def add_source_conversation(
        user_id: str,
        conversation_id: str,
        facts_added: int,
        facts_updated: int,
        facts_removed: int,
    ) -> None
        # Append a source_conversation entry to the audit trail
```

### 4.2 New Module: `backend/profile_agent.py`

```
@dataclass
class ProfileExtractionResult:
    changed: bool
    summary: str
    profile: dict  # The updated profile sections (basic_info, interests, etc.)


class ProfileAgent:
    """Extracts user profile facts from conversations."""

    def __init__(self, chat_client: AzureOpenAIChatClient)
        # Creates the ChatAgent with PROFILE_EXTRACTION_PROMPT

    async def extract_profile(
        self,
        existing_profile: dict | None,
        conversation_messages: list[dict],
        conversation_id: str,
    ) -> ProfileExtractionResult
        # 1. Build prompt with existing profile + conversation
        # 2. Run agent
        # 3. Parse JSON response
        # 4. Return result
```

### 4.3 New Environment Variables

```env
# User Profile Memory (Cosmos DB) — optional overrides
COSMOS_UPM_DATABASE_NAME=userprofiles      # default
COSMOS_UPM_CONTAINER_NAME=userprofiles     # default
```

No new dependencies — reuses `azure-cosmos` already in `pyproject.toml`.

---

## 5. API Design

All endpoints scoped to the authenticated user via `X-User-ID` header.

### 5.1 Get Profile

```
GET /profile
```

Returns the current user's profile, or `null`/`404` if none exists yet.

**Response (200):**
```json
{
  "user_id": "user-alice",
  "version": 3,
  "basic_info": { "name": "Alice Johnson", "location": "Seattle, WA" },
  "interests": ["hiking", "machine learning"],
  "habits": ["orders coffee beans monthly"],
  "preferences": { "shipping_preference": "express" },
  "status": { "recent_issues": "waiting for replacement" },
  "facts": ["Has two cats named Luna and Milo"],
  "source_conversations": [...],
  "created_at": "2026-02-08T10:00:00Z",
  "updated_at": "2026-02-10T12:00:00Z"
}
```

**Response (404):**
```json
{ "detail": "No profile found. Use 'Generate Profile' to create one." }
```

### 5.2 Generate / Update Profile from Conversation

```
POST /profile/generate
```

**Request Body:**
```json
{
  "conversation_id": "conv-abc-123"
}
```

**Flow:**
1. Validate user owns the conversation (Cosmos DB read).
2. Fetch existing profile (may be `null` for first-time).
3. Fetch conversation messages from Cosmos DB.
4. Run `ProfileAgent.extract_profile(existing, messages, conversation_id)`.
5. If `changed == true`: upsert profile in Cosmos DB, add source_conversation entry.
6. If `changed == false`: return existing profile with `"profile_changed": false`.

**Response (200):**
```json
{
  "profile_changed": true,
  "change_summary": "Added location (Portland), updated shipping preference to ground",
  "profile": { ... full profile ... }
}
```

**Error cases:**
- `404` — conversation not found or not owned by user
- `422` — conversation has no messages

### 5.3 Generate Profile from All Conversations

```
POST /profile/generate-all
```

Processes all (or recent N) conversations for the user to build a comprehensive profile from scratch or update an existing one.

**Request Body (optional):**
```json
{
  "limit": 20
}
```

**Flow:**
1. Fetch existing profile (may be `null`).
2. List recent N conversations for the user.
3. Filter out conversations already in `source_conversations` (skip reprocessing).
4. For each new conversation, run `ProfileAgent.extract_profile(current_profile, messages, conv_id)`.
5. Chain results — each extraction builds on the previous one's output.
6. Upsert final profile.

**Response (200):**
```json
{
  "profile_changed": true,
  "conversations_processed": 5,
  "conversations_skipped": 3,
  "change_summary": "Processed 5 conversations. Added 8 facts, updated 2.",
  "profile": { ... }
}
```

**Note:** This can be slow (sequential LLM calls). Returns synchronously for MVP. Consider streaming progress updates or background processing in the future.

### 5.4 Update Profile Manually

```
PUT /profile
```

Allows the user to manually edit their profile (e.g., correct information, add facts the agent missed).

**Request Body:**
```json
{
  "basic_info": { "location": "Portland, OR" },
  "interests": ["hiking", "cooking"],
  "habits": [],
  "preferences": { "shipping_preference": "ground" },
  "status": {},
  "facts": ["Birthday is in March"]
}
```

**Flow:**
1. Merge provided fields into existing profile (partial update — omitted fields are left unchanged).
2. Bump version.
3. Return updated profile.

**Response (200):** Full updated profile document.

### 5.5 Delete Profile

```
DELETE /profile
```

Hard-deletes the user's profile.

**Response (200):**
```json
{ "message": "Profile deleted successfully" }
```

**Error:** `404` if no profile exists.

### 5.6 API Summary Table

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/profile` | Get current user's profile |
| `POST` | `/profile/generate` | Generate/update profile from one conversation |
| `POST` | `/profile/generate-all` | Generate/update profile from all conversations |
| `PUT` | `/profile` | Manually edit profile |
| `DELETE` | `/profile` | Delete profile |

---

## 6. Server Integration (`server.py`)

### 6.1 Initialization

```python
from user_profile_memory import UserProfileMemoryStore
from profile_agent import ProfileAgent

profile_store = UserProfileMemoryStore()
profile_agent = ProfileAgent(chat_client=chat_client)

@app.on_event("startup")
async def startup_event():
    await conversation_store.initialize()
    await memory_store.initialize()
    await profile_store.initialize()       # ← new

@app.on_event("shutdown")
async def shutdown_event():
    await conversation_store.close()
    await memory_store.close()
    await profile_store.close()            # ← new
```

### 6.2 Endpoint Registration

```python
@app.get("/profile")                                 # get profile
@app.post("/profile/generate",    status_code=200)    # generate from 1 conversation
@app.post("/profile/generate-all", status_code=200)   # generate from all conversations
@app.put("/profile")                                   # manual edit
@app.delete("/profile")                                # delete profile
```

### 6.3 Pydantic Models

```python
class UserProfileResponse(BaseModel):
    user_id: str
    version: int
    basic_info: dict[str, str | None]
    interests: list[str]
    habits: list[str]
    preferences: dict[str, str | None]
    status: dict[str, str | None]
    facts: list[str]
    source_conversations: list[dict]
    created_at: str
    updated_at: str

class GenerateProfileRequest(BaseModel):
    conversation_id: str

class GenerateAllProfilesRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)

class UpdateProfileRequest(BaseModel):
    basic_info: dict[str, str | None] | None = None
    interests: list[str] | None = None
    habits: list[str] | None = None
    preferences: dict[str, str | None] | None = None
    status: dict[str, str | None] | None = None
    facts: list[str] | None = None

class GenerateProfileResponse(BaseModel):
    profile_changed: bool
    change_summary: str
    profile: UserProfileResponse

class GenerateAllProfilesResponse(BaseModel):
    profile_changed: bool
    conversations_processed: int
    conversations_skipped: int
    change_summary: str
    profile: UserProfileResponse
```

---

## 7. Frontend Design

### 7.1 Trigger: "Generate User Profile" Button

Located in the sidebar, as a button in the user card area at the bottom:

```
┌─────────────────────────────────┐
│  Chat                         ✕ │
│                                 │
│  ─ Sessions ────────────        │
│  ...                            │
│  ─ History ─────────────        │
│  ...                            │
│  ─ Memory ──────────────        │
│  ...                            │
│                                 │
│ ┌─────────────────────────────┐ │
│ │  AJ  Alice Johnson          │ │  ← click avatar/name → show profile
│ │       ┌──────────────────┐  │ │
│ │       │ Generate Profile │  │ │  ← button (visible when no profile exists
│ │       └──────────────────┘  │ │     or as "Update Profile" when it does)
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

**Button states:**
- **No profile exists**: Shows "Generate Profile" with `person_add` icon.
- **Profile exists**: Shows "Update Profile" with `refresh` icon.
- **Generating**: Shows spinner + "Generating..." (disabled).

### 7.2 Profile Display: Popover / Drawer on Avatar Click

When the user clicks their avatar or name in the sidebar bottom, a **slide-up drawer** (or **popover panel**) appears above the user card, still within the sidebar. This is the cleanest pattern because:
- It doesn't navigate away from the current view.
- It stays contextual (sidebar = user/session management).
- Dismissible with Escape or click-outside.

**Drawer mockup:**

```
┌─────────────────────────────────┐
│  Chat                         ✕ │
│                                 │
│ ┌─────────────────────────────┐ │
│ │  👤 User Profile         ✕  │ │  ← drawer header with close button
│ │                              │ │
│ │  ─ Basic Info ───────────── │ │
│ │  Name: Alice Johnson        │ │
│ │  Location: Seattle, WA      │ │
│ │  Occupation: Software Eng.  │ │
│ │                              │ │
│ │  ─ Interests ───────────── │ │
│ │  🏷️ hiking                  │ │
│ │  🏷️ machine learning        │ │
│ │  🏷️ cooking Italian food    │ │
│ │                              │ │
│ │  ─ Habits ─────────────── │ │
│ │  • orders coffee monthly    │ │
│ │  • prefers express shipping │ │
│ │                              │ │
│ │  ─ Preferences ──────────── │ │
│ │  Communication: concise     │ │
│ │  Shipping: express          │ │
│ │                              │ │
│ │  ─ Status ─────────────── │ │
│ │  Recent: waiting for ORD-003│ │
│ │                              │ │
│ │  ─ Notable Facts ────────── │ │
│ │  • Has two cats (Luna, Milo)│ │
│ │  • Allergic to peanuts      │ │
│ │                              │ │
│ │  ───────────────────────── │ │
│ │  Updated 2h ago · v3        │ │
│ │  [Update Profile] [Delete]  │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │  AJ  Alice Johnson     ▲   │ │  ← arrow indicates drawer is open
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

### 7.3 State Management

```typescript
// New state properties on NativeApp
@state() private userProfile: UserProfile | null = null;
@state() private profileDrawerOpen = false;
@state() private profileLoading = false;
@state() private profileGenerating = false;
```

### 7.4 TypeScript Interfaces

```typescript
export interface UserProfile {
  user_id: string;
  version: number;
  basic_info: Record<string, string | null>;
  interests: string[];
  habits: string[];
  preferences: Record<string, string | null>;
  status: Record<string, string | null>;
  facts: string[];
  source_conversations: ProfileSourceConversation[];
  created_at: string;
  updated_at: string;
}

export interface ProfileSourceConversation {
  conversation_id: string;
  extracted_at: string;
  facts_added: number;
  facts_updated: number;
  facts_removed: number;
}

export interface GenerateProfileResponse {
  profile_changed: boolean;
  change_summary: string;
  profile: UserProfile;
}

export interface GenerateAllProfilesResponse extends GenerateProfileResponse {
  conversations_processed: number;
  conversations_skipped: number;
}
```

### 7.5 Client Methods

```typescript
// Add to AGUIClient class:

async getProfile(): Promise<UserProfile | null> {
  // GET /profile — returns profile or null (404)
}

async generateProfile(conversationId: string): Promise<GenerateProfileResponse> {
  // POST /profile/generate { conversation_id }
}

async generateProfileFromAll(limit?: number): Promise<GenerateAllProfilesResponse> {
  // POST /profile/generate-all { limit }
}

async updateProfile(updates: Partial<UserProfile>): Promise<UserProfile> {
  // PUT /profile { ...updates }
}

async deleteProfile(): Promise<void> {
  // DELETE /profile
}
```

### 7.6 User Interaction Flows

#### Flow 1: First-Time Profile Generation

```
1. User sees "Generate Profile" button in sidebar bottom
2. Clicks button
3. Frontend calls POST /profile/generate-all { limit: 20 }
4. Button shows spinner + "Generating..."
5. Agent processes recent conversations sequentially
6. Response arrives with generated profile
7. Profile drawer auto-opens showing the new profile
8. Button text changes to "Update Profile"
```

#### Flow 2: Single-Conversation Update

```
1. User finishes a conversation
2. Optionally clicks "Update Profile" button (or a new icon on the
   conversation item similar to the memorize button)
3. Frontend calls POST /profile/generate { conversation_id }
4. If profile_changed == true, the drawer shows a brief toast:
   "Profile updated: Added location (Portland)"
5. If profile_changed == false, toast: "No new personal info found"
```

#### Flow 3: View Profile

```
1. User clicks their avatar/name in sidebar bottom
2. Profile drawer slides up / toggles open
3. If profile exists: show profile data
4. If no profile: show empty state with "Generate Profile" CTA
5. Click close (✕) or click avatar again to dismiss
```

---

## 8. Data Flow Diagrams

### 8.1 Profile Generation Flow

```
User clicks "Generate Profile" button
    │
    ▼
Frontend: POST /profile/generate-all { limit: 20 }
    │
    ▼
Backend (server.py):
    ├─ 1. Read existing profile from Cosmos DB (may be null)
    ├─ 2. List recent conversations from Cosmos DB
    ├─ 3. Filter out already-processed conversations
    ├─ 4. For each new conversation:
    │       ├─ Fetch messages from Cosmos DB
    │       ├─ Call ProfileAgent.extract_profile(current, messages, conv_id)
    │       │     └─ ChatAgent processes prompt → returns JSON
    │       ├─ If changed: update current profile in memory
    │       └─ Record source_conversation entry
    ├─ 5. Upsert final profile into Cosmos DB
    └─ 6. Return { profile_changed, change_summary, profile }
    │
    ▼
Frontend: Open profile drawer, display profile
```

### 8.2 Single-Conversation Update Flow

```
User clicks "Update Profile" or processes a specific conversation
    │
    ▼
Frontend: POST /profile/generate { conversation_id: "conv-xyz" }
    │
    ▼
Backend (server.py):
    ├─ 1. Validate user owns conversation
    ├─ 2. Read existing profile (may be null)
    ├─ 3. Fetch conversation messages
    ├─ 4. Call ProfileAgent.extract_profile(existing, messages, conv_id)
    │       └─ Agent returns { profile_changed, change_summary, profile }
    ├─ 5. If changed: upsert profile, add source_conversation entry
    └─ 6. Return response
    │
    ▼
Frontend: Show toast with change_summary, refresh profile if drawer is open
```

---

## 9. File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/user_profile_memory.py` | **New** | `UserProfileMemoryStore` — Cosmos DB CRUD for user profiles |
| `backend/profile_agent.py` | **New** | `ProfileAgent` — ChatAgent for extracting profile facts from conversations |
| `backend/server.py` | **Modify** | Add 5 profile endpoints, initialize `profile_store` + `profile_agent` |
| `frontend/src/client.ts` | **Modify** | Add profile API methods + TypeScript interfaces |
| `frontend/src/app.ts` | **Modify** | Add profile drawer UI, "Generate Profile" button, state management |

**No new dependencies** — the feature reuses:
- `azure-cosmos` (already in `pyproject.toml`)
- `agent-framework` ChatAgent (already in use)
- `AzureOpenAIChatClient` (already initialized)

**No database migrations** — Cosmos DB containers are created dynamically at startup.

---

## 10. Cosmos DB Considerations

Following the Azure Cosmos DB best practices:

1. **Partition key**: `/user_id` — each user profile is a single document in its own logical partition. Point reads are 1 RU.

2. **Item size**: Profile documents will be well under the 2 MB limit. Even with 20 source conversation entries and 20 items in each array, the document is ~2-5 KB.

3. **Embedding within one document**: All profile sections are embedded within a single document (not referenced). This is correct because:
   - They are always read/written together.
   - The total size is small.
   - There are no independently-queried subsections.

4. **Request Units**: Profile operations are lightweight:
   - `GET /profile` → 1 RU (point read)
   - `POST /profile/generate` → 1 RU (read) + 5-10 RU (upsert) = ~11 RU
   - The LLM API call dominates latency, not Cosmos DB.

5. **Separate database**: Using `userprofiles` database (separate from `conversationhistory`) for logical isolation. Both share the same Cosmos DB account and SDK client.

---

## 11. Differences from Conversation Memory

| Aspect | Conversation Memory | User Profile Memory |
|--------|--------------------|--------------------|
| **Scope** | One per conversation | One per user |
| **Storage** | PostgreSQL + pgvector | Cosmos DB |
| **Purpose** | Semantic search over past conversations | Persistent user knowledge |
| **Trigger** | Manual "Memorize" button on conversation | Manual "Generate Profile" button |
| **Data shape** | Summary text + vector embedding | Structured JSON document |
| **Agent task** | Summarize → embed | Extract facts → merge |
| **Update pattern** | Upsert (replace) | Merge (additive) |
| **Vector search** | Yes (pgvector cosine similarity) | No |
| **Cardinality** | N memories per user | 1 profile per user |

---

## 12. Open Questions / Future Considerations

1. **Privacy**: Profile data contains PII. Consider adding a consent mechanism or privacy notice before first generation. The delete endpoint allows users to erase their profile entirely.

2. **Profile-augmented chat**: The natural next step — inject the user profile into the agent's system prompt so the assistant remembers user preferences. Example: "I see you prefer express shipping — would you like to use that for this order?" Out of scope for this design.

3. **Automatic updates**: Currently opt-in (manual button). A future enhancement could automatically update the profile after each conversation (with a setting to enable/disable). This would add a `POST /profile/generate` call at the end of the `stream_agent_response` function in `server.py`.

4. **Profile editing UI**: The current design includes `PUT /profile` for manual edits, but the frontend only shows a read-only view. A future phase could add inline editing in the drawer (click a field to edit, save on blur).

5. **Multi-conversation processing speed**: `POST /profile/generate-all` processes conversations sequentially (each needs an LLM call). For 20 conversations, this could take 30-60 seconds. Consider:
   - Streaming progress updates via SSE.
   - Background task with polling for completion.
   - Batching: concatenate multiple short conversations into one agent call.

6. **Profile versioning / history**: The `version` field enables optimistic concurrency, but we don't keep old versions. If history is needed, consider storing a change log or using Cosmos DB change feed.

7. **Agent model choice**: The profile extraction agent uses the same deployment as the main chat agent (`AZURE_OPENAI_DEPLOYMENT_NAME`). If cost is a concern, a cheaper/faster model could be used for this task since it doesn't need tool calling.
