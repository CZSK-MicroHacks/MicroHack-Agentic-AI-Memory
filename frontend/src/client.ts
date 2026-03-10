/**
 * AG-UI SSE Client
 * Communicates with the AG-UI backend over Server-Sent Events.
 */

import { getAuthHeaders, type User } from './auth.js';

export interface AGUIEvent {
  type: string;
  [key: string]: unknown;
}

export interface StreamCallbacks {
  onTextContent: (delta: string) => void;
  onToolCallStart: (id: string, name: string) => void;
  onToolCallResult: (id: string, result: string) => void;
  onToolCallEnd: (id: string) => void;
  onError: (message: string) => void;
  onFinished: () => void;
}

export interface SessionInfo {
  session_id: string;
  title: string | null;
  created_at: string;
  message_count: number;
  last_activity: string | null;
}

export interface ToolCallRecord {
  call_id: string;
  name: string;
  arguments?: string;
}

export interface ToolResultRecord {
  call_id: string;
  result: string;
}

export interface SessionHistoryMessage {
  role: string;
  content: string;
  tool_calls?: ToolCallRecord[];
  tool_results?: ToolResultRecord[];
}

export interface SessionHistoryResult {
  messages: SessionHistoryMessage[];
  metadata: Record<string, unknown>;
}

export interface ConversationSummary {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: SessionHistoryMessage[];
  metadata: Record<string, unknown>;
}

export interface MemorySummary {
  id: string;
  conversation_id: string;
  user_id: string;
  summary: string;
  source_title: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface MemorySearchResultItem {
  id: string;
  conversation_id: string;
  summary: string;
  source_title: string | null;
  similarity: number;
  created_at: string;
}

export interface MemorySearchResponse {
  query: string;
  results: MemorySearchResultItem[];
}

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

export class AGUIClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    // Use provided URL, or runtime config injected by Docker, or default to /api for dev
    this.baseUrl = baseUrl ?? (window as any).__APP_CONFIG__?.apiBaseUrl ?? '/api';
  }

  private async authHeaders(): Promise<Record<string, string>> {
    return getAuthHeaders();
  }

  /* ── Auth ───────────────────────────────────────────────── */

  async getMe(): Promise<User> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/me`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* ── Session CRUD ──────────────────────────────────────── */

  async listSessions(): Promise<SessionInfo[]> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async createSession(title?: string): Promise<{ session_id: string }> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ title: title ?? null }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async getSession(sessionId: string): Promise<SessionInfo> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async updateSession(sessionId: string, title: string): Promise<SessionInfo> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async deleteSession(sessionId: string): Promise<void> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  async getSessionHistory(sessionId: string): Promise<SessionHistoryResult> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/sessions/${sessionId}/history`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { messages: data.messages ?? [], metadata: data.metadata ?? {} };
  }

  /* ── Conversation History (Cosmos DB) ────────────────── */

  async listConversations(limit = 50, offset = 0): Promise<ConversationSummary[]> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(
      `${this.baseUrl}/conversations?limit=${limit}&offset=${offset}`,
      { headers: { ...authHeaders } },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/conversations/${conversationId}`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async updateConversation(conversationId: string, title: string): Promise<void> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/conversations/${conversationId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/conversations/${conversationId}`, {
      method: 'DELETE',
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  /* ── Conversation Memory (PostgreSQL + pgvector) ───────── */

  async createMemory(conversationId: string): Promise<MemorySummary> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/memories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async listMemories(limit = 50, offset = 0): Promise<MemorySummary[]> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(
      `${this.baseUrl}/memories?limit=${limit}&offset=${offset}`,
      { headers: { ...authHeaders } },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async getMemory(conversationId: string): Promise<MemorySummary> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/memories/${conversationId}`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async deleteMemory(conversationId: string): Promise<void> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/memories/${conversationId}`, {
      method: 'DELETE',
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  async searchMemories(query: string, limit = 10): Promise<MemorySearchResponse> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/memories/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ query, limit }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* ── User Profile Memory ─────────────────────────────── */

  async getProfile(): Promise<UserProfile | null> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/profile`, {
      headers: { ...authHeaders },
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async generateProfile(conversationId: string): Promise<GenerateProfileResponse> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/profile/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async generateProfileFromAll(limit = 20): Promise<GenerateAllProfilesResponse> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/profile/generate-all`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ limit }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async updateProfile(updates: Partial<UserProfile>): Promise<UserProfile> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async deleteProfile(): Promise<void> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/profile`, {
      method: 'DELETE',
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  /* ── Prompt ──────────────────────────────────────────────── */

  async getPrompt(name: string): Promise<{ name: string; content: string }> {
    const authHeaders = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/prompts/${encodeURIComponent(name)}`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* ── SSE streaming ─────────────────────────────────────── */

  private parseSSEEvent(line: string): AGUIEvent | null {
    if (!line.startsWith('data: ')) return null;
    try {
      return JSON.parse(line.slice(6)) as AGUIEvent;
    } catch {
      return null;
    }
  }

  async sendMessage(
    message: string,
    threadId: string | null,
    ragMode: string,
    callbacks: StreamCallbacks,
  ): Promise<{ sessionId: string | null }> {
    const authHeaders = await this.authHeaders();
    const response = await fetch(`${this.baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({
        messages: [{ role: 'user', content: message }],
        thread_id: threadId,
        rag_mode: ragMode,
      }),
    });

    const sessionId = response.headers.get('X-Session-ID');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = this.parseSSEEvent(line);
          if (!event) continue;

          switch (event.type) {
            case 'TEXT_MESSAGE_CONTENT':
              callbacks.onTextContent(event.delta as string);
              break;
            case 'TOOL_CALL_START':
              callbacks.onToolCallStart(event.toolCallId as string, event.toolCallName as string);
              break;
            case 'TOOL_CALL_RESULT':
              callbacks.onToolCallResult(event.toolCallId as string, event.content as string);
              break;
            case 'TOOL_CALL_END':
              callbacks.onToolCallEnd(event.toolCallId as string);
              break;
            case 'RUN_ERROR':
              callbacks.onError(event.message as string);
              break;
            case 'RUN_FINISHED':
              callbacks.onFinished();
              break;
          }
        }
      }
    } catch (err) {
      callbacks.onError(err instanceof Error ? err.message : 'Unknown error');
    }

    return { sessionId };
  }
}
