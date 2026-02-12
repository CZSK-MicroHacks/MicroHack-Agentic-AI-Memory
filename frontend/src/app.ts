/**
 * A2UI Native App Shell
 *
 * Main application component. Chat messages with text are rendered as simple
 * bubbles. Tool-call results are converted to A2UI messages on the fly and
 * rendered with the native <a2ui-surface> renderer — no custom widget code.
 */

import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, query } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { marked } from 'marked';
import { AGUIClient, type SessionInfo, type ConversationSummary, type MemorySummary, type MemorySearchResponse, type MemorySearchResultItem, type UserProfile, type GenerateProfileResponse } from './client.js';
import type { User } from './auth.js';
import { A2UIProcessor, type SurfaceState } from './a2ui/processor.js';
import { convertToolResult, convertGenericResult } from './converters.js';

// Register the surface renderer custom element
import './a2ui/surface-renderer.js';

/* ── Data types ───────────────────────────────────────────── */

interface ToolCallInfo {
  id: string;
  name: string;
  result?: string;
  status: 'running' | 'completed';
  /** A2UI surface state rendered from the result, if any */
  surface?: SurfaceState;
  surfaceId?: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls: ToolCallInfo[];
  isStreaming?: boolean;
}

/* ── Component ────────────────────────────────────────────── */

@customElement('a2ui-native-app')
export class NativeApp extends LitElement {
  @state() private messages: ChatMessage[] = [];
  @state() private isLoading = false;
  @state() private sessionId: string | null = null;
  @state() private sidebarOpen = true;
  @state() private sessions: SessionInfo[] = [];
  @state() private editingSessionId: string | null = null;
  @state() private editingTitle = '';
  @state() private currentUser: User | null = null;
  @state() private conversations: ConversationSummary[] = [];
  @state() private editingConversationId: string | null = null;
  @state() private editingConversationTitle = '';
  @state() private activeConversationId: string | null = null;
  @state() private memorizingConversationId: string | null = null;
  @state() private memorizedConversationIds: Set<string> = new Set();
  @state() private memories: MemorySummary[] = [];
  @state() private selectedMemory: MemorySummary | null = null;
  @state() private memorySearchQuery = '';
  @state() private memorySearchResults: MemorySearchResultItem[] = [];
  @state() private memorySearchLoading = false;
  @state() private userProfile: UserProfile | null = null;
  @state() private profileDrawerOpen = false;
  @state() private profileLoading = false;
  @state() private profileGenerating = false;
  @state() private profileToast: string | null = null;
  @state() private promptModalOpen = false;
  @state() private promptContent: string | null = null;
  @state() private promptLoading = false;
  @state() private promptCopied = false;

  private buildId = ((window as any).__APP_CONFIG__?.buildId ?? '').trim();

  @query('.messages-area')
  private messagesArea!: HTMLElement;

  @query('input#msg-input')
  private inputEl!: HTMLInputElement;

  private client = new AGUIClient();

  /* ── Styles ─────────────────────────────────────────────── */

  static styles = css`
    /* Material Symbols – must be declared inside Shadow DOM */
    .material-symbols-outlined {
      font-family: 'Material Symbols Outlined';
      font-weight: normal;
      font-style: normal;
      font-size: 24px;
      line-height: 1;
      letter-spacing: normal;
      text-transform: none;
      display: inline-block;
      white-space: nowrap;
      word-wrap: normal;
      direction: ltr;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
      font-feature-settings: 'liga';
    }

    :host {
      display: flex;
      height: 100vh;
      width: 100%;
      color: light-dark(var(--n-10, #171717), var(--n-90, #e2e2e2));
      font-size: 14px;
      line-height: 1.6;
    }

    /* ── Sidebar ────────────────────────────────────────── */
    .sidebar {
      display: flex;
      flex-direction: column;
      width: 260px;
      min-width: 260px;
      height: 100vh;
      border-right: 1px solid light-dark(var(--n-95), var(--n-25));
      background: light-dark(var(--n-98), var(--n-10));
      transition: margin-left 0.25s ease, opacity 0.25s ease;
      overflow: hidden;
      position: relative;
    }
    .sidebar.collapsed {
      margin-left: -260px;
      opacity: 0;
      pointer-events: none;
    }

    .sidebar-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 12px 12px 16px;
      height: 52px;
    }
    .sidebar-header h2 {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: light-dark(var(--n-50), var(--n-60));
    }
    .sidebar-actions { display: flex; gap: 2px; }

    .icon-btn {
      width: 32px; height: 32px;
      border: none;
      border-radius: 6px;
      background: transparent;
      color: light-dark(var(--n-50), var(--n-60));
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }
    .icon-btn:hover {
      background: light-dark(var(--n-95), var(--n-20));
      color: light-dark(var(--n-10), var(--n-90));
    }

    .session-list {
      flex: 1;
      overflow-y: auto;
      padding: 4px 8px;
    }
    .session-list::-webkit-scrollbar { width: 4px; }
    .session-list::-webkit-scrollbar-track { background: transparent; }
    .session-list::-webkit-scrollbar-thumb {
      background: light-dark(var(--n-80), var(--n-30));
      border-radius: 2px;
    }

    .session-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      border: none;
      transition: background 0.12s;
      margin-bottom: 1px;
    }
    .session-item:hover {
      background: light-dark(var(--n-95), var(--n-20));
    }
    .session-item.active {
      background: light-dark(var(--n-95), var(--n-20));
    }
    .session-icon {
      flex-shrink: 0;
      color: light-dark(var(--n-60), var(--n-50));
    }
    .session-item.active .session-icon {
      color: light-dark(var(--n-40), var(--n-70));
    }
    .session-info {
      flex: 1;
      min-width: 0;
    }
    .session-title {
      font-size: 13px;
      font-weight: 400;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .session-meta {
      font-size: 11px;
      color: light-dark(var(--n-60), var(--n-50));
      margin-top: 1px;
    }
    .session-item-actions {
      display: flex;
      gap: 0;
      opacity: 0;
      transition: opacity 0.12s;
    }
    .session-item:hover .session-item-actions,
    .session-item.active .session-item-actions {
      opacity: 1;
    }
    .session-item-actions .icon-btn {
      width: 26px; height: 26px;
    }
    .session-item-actions .icon-btn .material-symbols-outlined {
      font-size: 15px;
    }

    /* Inline rename input */
    .rename-input {
      flex: 1;
      min-width: 0;
      padding: 3px 8px;
      border: 1px solid light-dark(var(--n-80), var(--n-30));
      border-radius: 6px;
      background: light-dark(var(--n-100), var(--n-15));
      font-family: var(--font-family, inherit);
      font-size: 13px;
      color: light-dark(var(--n-10), var(--n-90));
      outline: none;
    }
    .rename-input:focus {
      border-color: light-dark(var(--p-50), var(--p-60));
    }

    .no-sessions {
      text-align: center;
      padding: 40px 16px;
      color: light-dark(var(--n-60), var(--n-50));
      font-size: 13px;
    }
    .no-sessions .material-symbols-outlined {
      font-size: 32px;
      display: block;
      margin-bottom: 8px;
      color: light-dark(var(--n-80), var(--n-30));
    }

    /* ── Sidebar section divider ───────────────────────── */
    .sidebar-section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 14px 12px 6px 16px;
    }
    .sidebar-section-header h3 {
      margin: 0;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: light-dark(var(--n-50), var(--n-60));
    }
    .sidebar-section-header hr {
      flex: 1;
      border: none;
      border-top: 1px solid light-dark(var(--n-90), var(--n-25));
    }
    .no-conversations {
      text-align: center;
      padding: 16px;
      color: light-dark(var(--n-60), var(--n-50));
      font-size: 12px;
    }

    /* ── User profile card (sidebar bottom) — see profile-drawer section for full styles ── */
    .user-avatar {
      flex-shrink: 0;
      width: 32px; height: 32px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      background: light-dark(var(--n-80), var(--n-30));
      color: light-dark(var(--n-100), var(--n-90));
    }
    .user-name {
      font-size: 13px;
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .user-meta {
      display: flex;
      flex-direction: column;
      min-width: 0;
      flex: 1;
    }
    .build-id {
      font-size: 11px;
      color: light-dark(var(--n-60), var(--n-50));
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-top: 1px;
    }
    .sidebar-build-id {
      padding: 6px 16px 10px;
      font-size: 11px;
      color: light-dark(var(--n-60), var(--n-50));
      border-top: 1px solid light-dark(var(--n-95), var(--n-25));
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* ── Main area ──────────────────────────────────────── */
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      max-width: 100%;
      background: light-dark(var(--n-100), var(--n-15));
    }

    /* ── Header ─────────────────────────────────────────── */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      height: 52px;
      border-bottom: 1px solid light-dark(var(--n-95), var(--n-25));
      background: light-dark(var(--n-100), var(--n-15));
    }
    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .logo {
      width: 32px; height: 32px;
      border-radius: 8px;
      background: light-dark(var(--n-10), var(--n-90));
      color: light-dark(var(--n-100), var(--n-10));
      display: flex; align-items: center; justify-content: center;
    }
    .title h1 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .title p  {
      margin: 0;
      font-size: 12px;
      color: light-dark(var(--n-60), var(--n-50));
    }
    .header-actions { display: flex; gap: 4px; align-items: center; }
    .hdr-btn {
      padding: 6px 12px;
      border: 1px solid light-dark(var(--n-90), var(--n-30));
      border-radius: 6px;
      background: transparent;
      color: light-dark(var(--n-40), var(--n-70));
      font-family: var(--font-family, inherit);
      font-size: 13px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .hdr-btn:hover { background: light-dark(var(--n-95), var(--n-20)); }
    .theme-btn {
      width: 32px; height: 32px; padding: 0; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
    }

    /* ── Messages ────────────────────────────────────────── */
    .messages-area {
      flex: 1;
      overflow-y: auto;
      padding: 0;
    }
    .messages-area::-webkit-scrollbar { width: 6px; }
    .messages-area::-webkit-scrollbar-track { background: transparent; }
    .messages-area::-webkit-scrollbar-thumb {
      background: light-dark(var(--n-80), var(--n-30));
      border-radius: 3px;
    }
    .messages-container {
      display: flex;
      flex-direction: column;
      min-height: 100%;
      max-width: 768px;
      margin: 0 auto;
      padding: 16px 24px;
    }

    /* ── Welcome ─────────────────────────────────────────── */
    .welcome {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 48px 24px;
      animation: fadeIn 0.4s ease-out;
    }
    .welcome-logo {
      width: 48px; height: 48px;
      border-radius: 12px;
      background: light-dark(var(--n-10), var(--n-90));
      color: light-dark(var(--n-100), var(--n-10));
      display: flex; align-items: center; justify-content: center;
      margin-bottom: 20px;
    }
    .welcome h2 {
      margin: 0 0 8px;
      font-size: 22px;
      font-weight: 600;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .welcome p {
      margin: 0 0 28px;
      color: light-dark(var(--n-50), var(--n-60));
      max-width: 420px;
      font-size: 14px;
      line-height: 1.5;
    }
    .suggestions {
      display: flex;
      flex-direction: column;
      gap: 8px;
      width: 100%;
      max-width: 400px;
    }
    .sug-btn {
      padding: 12px 16px;
      border: 1px solid light-dark(var(--n-90), var(--n-25));
      border-radius: 12px;
      background: light-dark(var(--n-100), var(--n-20));
      color: light-dark(var(--n-30), var(--n-80));
      font-family: var(--font-family, inherit);
      font-size: 13px;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
      text-align: left;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .sug-btn:hover {
      background: light-dark(var(--n-98), var(--n-25));
      border-color: light-dark(var(--n-80), var(--n-35));
    }
    .sug-btn .material-symbols-outlined {
      font-size: 16px;
      color: light-dark(var(--n-60), var(--n-50));
    }

    /* ── Chat message (ChatGPT-style full-width rows) ──── */
    .msg {
      display: flex;
      gap: 16px;
      padding: 20px 0;
      animation: fadeIn 0.25s ease-out;
    }
    .msg + .msg {
      border-top: none;
    }
    .msg.user {
      flex-direction: row;
    }
    .avatar {
      flex-shrink: 0;
      width: 28px; height: 28px;
      border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      margin-top: 2px;
    }
    .avatar.user {
      background: light-dark(var(--p-50), var(--p-60));
      color: white;
    }
    .avatar.assistant {
      background: light-dark(var(--n-10), var(--n-90));
      color: light-dark(var(--n-100), var(--n-10));
    }
    .msg-body {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
    }
    .msg.user .msg-body {
      align-items: flex-start;
    }
    .msg-role {
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 4px;
      color: light-dark(var(--n-10), var(--n-90));
    }

    /* No bubble — flat text like ChatGPT */
    .bubble {
      padding: 0;
      border-radius: 0;
      line-height: 1.65;
      word-break: break-word;
      font-size: 14px;
      color: light-dark(var(--n-10), var(--n-90));
    }
    /* Markdown typography */
    .bubble p { margin: 0 0 10px; }
    .bubble p:last-child { margin-bottom: 0; }
    .bubble h1, .bubble h2, .bubble h3, .bubble h4 {
      margin: 16px 0 8px; line-height: 1.3;
    }
    .bubble h1 { font-size: 1.3em; }
    .bubble h2 { font-size: 1.15em; }
    .bubble h3 { font-size: 1.05em; }
    .bubble ul, .bubble ol { margin: 4px 0; padding-left: 20px; }
    .bubble li { margin-bottom: 4px; }
    .bubble code {
      font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
      font-size: 0.85em;
      padding: 2px 6px;
      border-radius: 4px;
      background: light-dark(var(--n-95), var(--n-20));
    }
    .bubble pre {
      margin: 12px 0;
      padding: 14px 16px;
      border-radius: 8px;
      overflow-x: auto;
      background: light-dark(var(--n-10), var(--n-5));
      color: light-dark(var(--n-95), var(--n-90));
    }
    .bubble pre code {
      padding: 0;
      background: none;
      color: inherit;
    }
    .bubble blockquote {
      margin: 8px 0;
      padding: 4px 14px;
      border-left: 3px solid light-dark(var(--n-80), var(--n-35));
      color: light-dark(var(--n-40), var(--n-60));
    }
    .bubble a {
      color: light-dark(var(--p-40), var(--p-70));
      text-decoration: underline;
      text-underline-offset: 2px;
    }
    .bubble table {
      border-collapse: collapse;
      margin: 10px 0;
      font-size: 0.92em;
    }
    .bubble th, .bubble td {
      border: 1px solid light-dark(var(--n-90), var(--n-30));
      padding: 6px 10px;
    }
    .bubble th {
      background: light-dark(var(--n-98), var(--n-20));
      font-weight: 600;
    }
    .bubble strong { font-weight: 600; }

    /* User messages — subtle background */
    .msg.user .bubble {
      background: none;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .msg.assistant .bubble {
      background: none;
      color: light-dark(var(--n-10), var(--n-90));
    }

    /* ── Tool call indicator ───────────────────────────────── */
    .tool-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      margin-bottom: 10px;
      border-radius: 6px;
      background: light-dark(var(--n-98), var(--n-20));
      border: 1px solid light-dark(var(--n-90), var(--n-25));
      font-size: 12px;
      color: light-dark(var(--n-50), var(--n-60));
    }
    .tool-indicator .spinner {
      width: 12px; height: 12px;
      border: 1.5px solid light-dark(var(--n-80), var(--n-30));
      border-left-color: light-dark(var(--n-40), var(--n-70));
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    .tool-indicator .material-symbols-outlined {
      font-size: 14px;
      color: light-dark(#16a34a, #4ade80);
    }
    .tool-name {
      font-weight: 500;
      font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
      font-size: 11px;
      color: light-dark(var(--n-40), var(--n-70));
    }

    /* ── A2UI surface wrapper ──────────────────────────────── */
    .surface-wrapper {
      margin-bottom: 10px;
      animation: fadeIn 0.3s ease-out;
    }

    /* ── Streaming cursor ──────────────────────────────────── */
    .cursor {
      display: inline-block;
      width: 2px; height: 18px;
      background: light-dark(var(--n-40), var(--n-60));
      margin-left: 1px;
      vertical-align: text-bottom;
      animation: blink 1s step-end infinite;
    }
    .loading-dots {
      display: flex;
      gap: 4px;
      padding: 4px 0;
    }
    .loading-dots span {
      width: 6px; height: 6px;
      background: light-dark(var(--n-60), var(--n-50));
      border-radius: 50%;
      animation: bounce 1.4s infinite ease-in-out both;
    }
    .loading-dots span:nth-child(1) { animation-delay: -0.32s; }
    .loading-dots span:nth-child(2) { animation-delay: -0.16s; }

    /* ── Input ────────────────────────────────────────────── */
    .input-area {
      padding: 12px 24px 20px;
      background: light-dark(var(--n-100), var(--n-15));
    }
    .input-row {
      display: flex;
      gap: 0;
      max-width: 768px;
      margin: 0 auto;
      border: 1px solid light-dark(var(--n-90), var(--n-25));
      border-radius: 16px;
      background: light-dark(var(--n-100), var(--n-20));
      overflow: hidden;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .input-row:focus-within {
      border-color: light-dark(var(--n-70), var(--n-40));
      box-shadow: 0 0 0 1px light-dark(var(--n-70), var(--n-40));
    }
    .input-row input {
      flex: 1;
      border: none;
      padding: 14px 16px;
      background: transparent;
      font-size: 14px;
      font-family: var(--font-family, inherit);
      color: light-dark(var(--n-10), var(--n-90));
      outline: none;
    }
    .input-row input::placeholder {
      color: light-dark(var(--n-60), var(--n-50));
    }
    .send-btn {
      display: flex; align-items: center; justify-content: center;
      width: 40px; height: 40px;
      margin: 4px 4px 4px 0;
      border-radius: 10px;
      border: none;
      background: light-dark(var(--n-10), var(--n-90));
      color: light-dark(var(--n-100), var(--n-10));
      cursor: pointer;
      transition: opacity 0.15s;
    }
    .send-btn:disabled { opacity: 0.3; cursor: default; }
    .send-btn:not(:disabled):hover { opacity: 0.85; }
    .input-footer {
      text-align: center; margin-top: 8px;
      font-size: 11px; color: light-dark(var(--n-60), var(--n-50));
    }

    /* ── Responsive ───────────────────────────────────────── */
    @media (max-width: 768px) {
      .sidebar { width: 240px; min-width: 240px; }
      .sidebar.collapsed { margin-left: -240px; }
      .messages-container { padding: 12px 16px; }
      .input-area { padding: 10px 16px 16px; }
    }

    /* ── Memory search ────────────────────────────────────── */
    .memory-search-input {
      width: 100%;
      padding: 8px 12px;
      border: 1px solid light-dark(var(--n-80), var(--n-30));
      border-radius: 8px;
      background: light-dark(var(--n-100), var(--n-15));
      font-family: var(--font-family, inherit);
      font-size: 12px;
      color: light-dark(var(--n-10), var(--n-90));
      outline: none;
      box-sizing: border-box;
    }
    .memory-search-input:focus {
      border-color: light-dark(var(--p-50), var(--p-60));
    }
    .memory-search-input::placeholder {
      color: light-dark(var(--n-60), var(--n-50));
    }
    .memory-search-wrapper {
      padding: 4px 12px 8px;
    }
    .memory-result-item {
      padding: 8px 12px;
      margin: 2px 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.12s;
    }
    .memory-result-item:hover {
      background: light-dark(var(--n-95), var(--n-20));
    }
    .memory-result-summary {
      font-size: 12px;
      color: light-dark(var(--n-30), var(--n-75));
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .memory-result-meta {
      font-size: 10px;
      color: light-dark(var(--n-60), var(--n-50));
      margin-top: 2px;
    }
    .memory-badge {
      font-size: 9px;
      padding: 1px 5px;
      border-radius: 4px;
      background: light-dark(#e0f2fe, #1e3a5f);
      color: light-dark(#0369a1, #7dd3fc);
      font-weight: 500;
      margin-left: 4px;
    }

    /* Memorize button spinner */
    .icon-btn .mini-spinner {
      width: 14px; height: 14px;
      border: 1.5px solid light-dark(var(--n-80), var(--n-30));
      border-left-color: light-dark(var(--n-40), var(--n-70));
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    /* ── Memory list items ─────────────────────────────────── */
    .memory-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.12s;
      margin-bottom: 1px;
    }
    .memory-item:hover {
      background: light-dark(var(--n-95), var(--n-20));
    }
    .memory-item.active {
      background: light-dark(var(--n-95), var(--n-20));
    }
    .memory-item-icon {
      flex-shrink: 0;
      color: light-dark(#0369a1, #7dd3fc);
    }
    .memory-item-info {
      flex: 1;
      min-width: 0;
    }
    .memory-item-title {
      font-size: 13px;
      font-weight: 400;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .memory-item-preview {
      font-size: 11px;
      color: light-dark(var(--n-60), var(--n-50));
      margin-top: 1px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .memory-item-actions {
      display: flex;
      gap: 0;
      opacity: 0;
      transition: opacity 0.12s;
    }
    .memory-item:hover .memory-item-actions {
      opacity: 1;
    }
    .memory-item-actions .icon-btn {
      width: 26px; height: 26px;
    }
    .memory-item-actions .icon-btn .material-symbols-outlined {
      font-size: 15px;
    }

    /* ── Profile drawer (overlays sidebar content) ──────── */
    .profile-drawer {
      position: absolute;
      bottom: 56px;
      left: 0; right: 0;
      top: 0;
      background: light-dark(var(--n-98), var(--n-10));
      z-index: 10;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: slideUp 0.25s ease-out;
    }
    @keyframes slideUp {
      from { transform: translateY(100%); opacity: 0; }
      to   { transform: translateY(0);    opacity: 1; }
    }
    .profile-drawer-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      border-bottom: 1px solid light-dark(var(--n-90), var(--n-25));
    }
    .profile-drawer-header h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .profile-drawer-body {
      flex: 1;
      overflow-y: auto;
      padding: 12px 16px;
    }
    .profile-drawer-body::-webkit-scrollbar { width: 4px; }
    .profile-drawer-body::-webkit-scrollbar-track { background: transparent; }
    .profile-drawer-body::-webkit-scrollbar-thumb {
      background: light-dark(var(--n-80), var(--n-30));
      border-radius: 2px;
    }
    .profile-section {
      margin-bottom: 16px;
    }
    .profile-section h4 {
      margin: 0 0 6px;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: light-dark(var(--n-50), var(--n-60));
    }
    .profile-kv {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 3px 10px;
      font-size: 12px;
    }
    .profile-kv dt {
      color: light-dark(var(--n-50), var(--n-60));
      font-weight: 500;
    }
    .profile-kv dd {
      margin: 0;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .profile-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .profile-tag {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      background: light-dark(var(--n-95), var(--n-20));
      color: light-dark(var(--n-30), var(--n-80));
    }
    .profile-list {
      list-style: none;
      margin: 0;
      padding: 0;
      font-size: 12px;
      color: light-dark(var(--n-20), var(--n-80));
    }
    .profile-list li {
      padding: 2px 0;
    }
    .profile-list li::before {
      content: "•";
      margin-right: 6px;
      color: light-dark(var(--n-60), var(--n-50));
    }
    .profile-footer {
      padding: 10px 16px;
      border-top: 1px solid light-dark(var(--n-90), var(--n-25));
      font-size: 11px;
      color: light-dark(var(--n-60), var(--n-50));
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .profile-footer-actions {
      display: flex;
      gap: 4px;
    }
    .profile-empty {
      text-align: center;
      padding: 40px 16px;
      color: light-dark(var(--n-50), var(--n-60));
      font-size: 13px;
    }
    .profile-empty .material-symbols-outlined {
      font-size: 36px;
      display: block;
      margin-bottom: 12px;
      color: light-dark(var(--n-80), var(--n-30));
    }
    .profile-gen-btn {
      margin-top: 12px;
      padding: 8px 16px;
      border: 1px solid light-dark(var(--n-80), var(--n-30));
      border-radius: 8px;
      background: light-dark(var(--n-100), var(--n-20));
      color: light-dark(var(--n-30), var(--n-80));
      font-family: var(--font-family, inherit);
      font-size: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }
    .profile-gen-btn:hover {
      background: light-dark(var(--n-95), var(--n-25));
    }
    .profile-gen-btn:disabled {
      opacity: 0.5;
      cursor: default;
    }

    /* ── User card (clickable) ─────────────────────────── */
    .user-card {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 10px;
      padding: 12px 16px;
      border-top: 1px solid light-dark(var(--n-95), var(--n-25));
      cursor: pointer;
      transition: background 0.12s;
      position: relative;
    }
    .user-card:hover {
      background: light-dark(var(--n-95), var(--n-20));
    }

    /* ── Toast notification ────────────────────────────── */
    .profile-toast {
      position: fixed;
      bottom: 80px;
      left: 50%;
      transform: translateX(-50%);
      padding: 10px 20px;
      border-radius: 8px;
      background: light-dark(var(--n-15), var(--n-85));
      color: light-dark(var(--n-95), var(--n-10));
      font-size: 13px;
      z-index: 1000;
      animation: fadeIn 0.25s ease-out;
      max-width: 400px;
      text-align: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .memory-detail {
      display: flex;
      flex-direction: column;
      min-height: 100%;
      max-width: 768px;
      margin: 0 auto;
      padding: 32px 24px;
      animation: fadeIn 0.25s ease-out;
    }
    .memory-detail-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
    }
    .memory-detail-icon {
      width: 40px; height: 40px;
      border-radius: 10px;
      background: light-dark(#e0f2fe, #1e3a5f);
      color: light-dark(#0369a1, #7dd3fc);
      display: flex; align-items: center; justify-content: center;
    }
    .memory-detail-title {
      flex: 1;
    }
    .memory-detail-title h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .memory-detail-title p {
      margin: 2px 0 0;
      font-size: 12px;
      color: light-dark(var(--n-60), var(--n-50));
    }
    .memory-detail-section {
      margin-bottom: 20px;
    }
    .memory-detail-section h3 {
      margin: 0 0 8px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: light-dark(var(--n-50), var(--n-60));
    }
    .memory-detail-summary {
      font-size: 14px;
      line-height: 1.65;
      color: light-dark(var(--n-10), var(--n-90));
      background: light-dark(var(--n-98), var(--n-20));
      border-radius: 12px;
      padding: 16px 20px;
    }
    .memory-detail-meta {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 6px 16px;
      font-size: 13px;
    }
    .memory-detail-meta dt {
      color: light-dark(var(--n-50), var(--n-60));
      font-weight: 500;
    }
    .memory-detail-meta dd {
      margin: 0;
      color: light-dark(var(--n-10), var(--n-90));
    }
    .memory-detail-actions {
      margin-top: 16px;
      display: flex;
      gap: 8px;
    }
    .memory-detail-actions button {
      padding: 8px 16px;
      border: 1px solid light-dark(var(--n-90), var(--n-30));
      border-radius: 8px;
      background: transparent;
      color: light-dark(var(--n-40), var(--n-70));
      font-family: var(--font-family, inherit);
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }
    .memory-detail-actions button:hover {
      background: light-dark(var(--n-95), var(--n-20));
    }

    /* ── Prompt modal ─────────────────────────────────────── */
    .prompt-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.45);
      z-index: 900;
      display: flex;
      align-items: center;
      justify-content: center;
      animation: fadeIn 0.15s ease-out;
    }
    .prompt-card {
      width: 92%;
      max-width: 860px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      border-radius: 14px;
      background: light-dark(var(--n-100), var(--n-15));
      box-shadow: 0 8px 30px rgba(0,0,0,0.25);
      overflow: hidden;
      animation: fadeIn 0.2s ease-out;
    }
    .prompt-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid light-dark(var(--n-90), var(--n-25));
    }
    .prompt-card-header h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: light-dark(var(--n-10), var(--n-90));
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .prompt-header-actions {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .prompt-copy-btn {
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border: 1px solid light-dark(var(--n-90), var(--n-30));
      border-radius: 6px;
      background: transparent;
      color: light-dark(var(--n-50), var(--n-60));
      font-family: var(--font-family, inherit);
      font-size: 12px;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }
    .prompt-copy-btn:hover {
      background: light-dark(var(--n-95), var(--n-20));
      color: light-dark(var(--n-10), var(--n-90));
    }
    .prompt-copy-btn.copied {
      color: light-dark(#16a34a, #4ade80);
      border-color: light-dark(#16a34a, #4ade80);
    }
    .prompt-card-body {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
    }
    .prompt-card-body::-webkit-scrollbar { width: 4px; }
    .prompt-card-body::-webkit-scrollbar-track { background: transparent; }
    .prompt-card-body::-webkit-scrollbar-thumb {
      background: light-dark(var(--n-80), var(--n-30));
      border-radius: 2px;
    }
    .prompt-code {
      margin: 0;
      padding: 16px 20px;
      border-radius: 10px;
      background: light-dark(var(--n-10), var(--n-5));
      color: light-dark(var(--n-90), var(--n-85));
      font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
      font-size: 12.5px;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-x: auto;
    }
    .prompt-loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px;
      color: light-dark(var(--n-60), var(--n-50));
      font-size: 13px;
      gap: 8px;
    }

    /* ── Animations ───────────────────────────────────────── */
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes blink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }
    @keyframes bounce {
      0%,80%,100% { transform: scale(0); }
      40% { transform: scale(1); }
    }
  `;

  /* ── Lifecycle ──────────────────────────────────────────── */

  connectedCallback() {
    super.connectedCallback();
    this.updateComplete.then(() => this.inputEl?.focus());
    this.fetchCurrentUser();
    this.refreshSessions();
    this.refreshConversations();
    this.refreshMemorizedIds();
    this.fetchProfile();
  }

  /* ── Helpers ────────────────────────────────────────────── */

  private async fetchCurrentUser() {
    try {
      this.currentUser = await this.client.getMe();
    } catch (err) {
      console.error('Failed to fetch current user:', err);
    }
  }

  private parseMarkdown(text: string): string {
    if (!text) return '';
    return marked.parse(text, { async: false, breaks: true }) as string;
  }

  private scrollToBottom() {
    requestAnimationFrame(() => {
      if (this.messagesArea) this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
    });
  }

  private toggleTheme() {
    const cs = getComputedStyle(document.body).colorScheme;
    if (cs === 'dark') {
      document.body.classList.add('light');
      document.body.classList.remove('dark');
    } else {
      document.body.classList.add('dark');
      document.body.classList.remove('light');
    }
  }

  private toggleSidebar() {
    this.sidebarOpen = !this.sidebarOpen;
  }

  private formatDate(iso: string | null): string {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return 'just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffH = Math.floor(diffMin / 60);
      if (diffH < 24) return `${diffH}h ago`;
      const diffD = Math.floor(diffH / 24);
      if (diffD < 7) return `${diffD}d ago`;
      return d.toLocaleDateString();
    } catch {
      return '';
    }
  }

  /* ── Session CRUD ───────────────────────────────────────── */

  private async refreshSessions() {
    try {
      this.sessions = await this.client.listSessions();
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }

  private async handleCreateSession() {
    try {
      const { session_id } = await this.client.createSession('New Chat');
      this.sessionId = session_id;
      this.messages = [];
      await this.refreshSessions();
      this.updateComplete.then(() => this.inputEl?.focus());
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  }

  private async handleSelectSession(id: string) {
    if (id === this.sessionId) return;
    this.sessionId = id;
    this.activeConversationId = null; // deselect conversation
    this.messages = [];

    try {
      const history = await this.client.getSessionHistory(id);
      this.messages = this.buildChatMessagesFromHistory(history);
      this.scrollToBottom();
    } catch (err) {
      console.error('Failed to load history:', err);
    }
    this.updateComplete.then(() => this.inputEl?.focus());
  }

  /**
   * Convert a list of SessionHistoryMessages (from sessions or conversations)
   * into ChatMessage[] with reconstructed A2UI surfaces.
   */
  private buildChatMessagesFromHistory(
    history: import('./client.js').SessionHistoryMessage[],
  ): ChatMessage[] {
    // First pass: collect tool results keyed by call_id
    const resultsByCallId = new Map<string, { name: string; result: string }>();
    for (const m of history) {
      if (m.tool_calls) {
        for (const tc of m.tool_calls) {
          resultsByCallId.set(tc.call_id, { name: tc.name, result: '' });
        }
      }
      if (m.tool_results) {
        for (const tr of m.tool_results) {
          const existing = resultsByCallId.get(tr.call_id);
          if (existing) existing.result = tr.result;
        }
      }
    }

    // Second pass: build ChatMessage array, attaching tool surfaces to assistant messages
    const msgs: ChatMessage[] = [];
    const pendingToolCalls: ToolCallInfo[] = [];

    for (const m of history) {
      if (m.tool_calls) {
        for (const tc of m.tool_calls) {
          const entry = resultsByCallId.get(tc.call_id);
          const toolInfo: ToolCallInfo = {
            id: tc.call_id,
            name: tc.name,
            status: 'completed',
            result: entry?.result,
          };
          if (entry?.result) {
            const surfaceId = `tool-${tc.call_id}`;
            const a2uiMsgs = convertToolResult(tc.name, entry.result, surfaceId)
              ?? convertGenericResult(tc.name, entry.result, surfaceId);
            const processor = new A2UIProcessor();
            processor.processMessages(a2uiMsgs);
            const surface = processor.getReadySurfaces().get(surfaceId);
            if (surface) {
              toolInfo.surface = surface;
              toolInfo.surfaceId = surfaceId;
            }
          }
          pendingToolCalls.push(toolInfo);
        }
        continue;
      }

      if (m.tool_results && m.role !== 'assistant' && m.role !== 'user') continue;

      if (m.role === 'user' || m.role === 'assistant') {
        const chatMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: m.role as 'user' | 'assistant',
          content: m.content,
          toolCalls: [],
        };
        if (m.role === 'assistant' && pendingToolCalls.length > 0) {
          chatMsg.toolCalls = [...pendingToolCalls];
          pendingToolCalls.length = 0;
        }
        msgs.push(chatMsg);
      }
    }
    return msgs;
  }

  private startRenameSession(id: string, currentTitle: string | null, e: Event) {
    e.stopPropagation();
    this.editingSessionId = id;
    this.editingTitle = currentTitle ?? '';
    // Auto-focus the rename input after render
    this.updateComplete.then(() => {
      const input = this.shadowRoot?.querySelector('.rename-input') as HTMLInputElement | null;
      input?.focus();
      input?.select();
    });
  }

  private async commitRename() {
    if (!this.editingSessionId) return;
    const title = this.editingTitle.trim();
    if (title) {
      try {
        await this.client.updateSession(this.editingSessionId, title);
        await this.refreshSessions();
      } catch (err) {
        console.error('Failed to rename:', err);
      }
    }
    this.editingSessionId = null;
    this.editingTitle = '';
  }

  private handleRenameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      this.commitRename();
    } else if (e.key === 'Escape') {
      this.editingSessionId = null;
      this.editingTitle = '';
    }
  }

  private async handleDeleteSession(id: string, e: Event) {
    e.stopPropagation();
    try {
      await this.client.deleteSession(id);
      if (this.sessionId === id) {
        this.sessionId = null;
        this.messages = [];
      }
      await this.refreshSessions();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  }

  private newChat() {
    this.sessionId = null;
    this.activeConversationId = null;
    this.messages = [];
    this.updateComplete.then(() => this.inputEl?.focus());
  }

  /* ── Conversation History CRUD ──────────────────────────── */

  private async refreshConversations() {
    try {
      this.conversations = await this.client.listConversations();
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  }

  private async handleSelectConversation(id: string) {
    if (id === this.activeConversationId) return;
    this.activeConversationId = id;
    this.sessionId = null; // deselect any live session
    this.messages = [];

    try {
      const conv = await this.client.getConversation(id);
      const msgs = this.buildChatMessagesFromHistory(conv.messages);
      this.messages = msgs;
      this.scrollToBottom();
    } catch (err) {
      console.error('Failed to load conversation:', err);
    }
    this.updateComplete.then(() => this.inputEl?.focus());
  }

  /** Resume a conversation: re-attach to the session so new messages
   *  go to the same thread and get persisted. */
  private resumeConversation(conversationId: string) {
    this.sessionId = conversationId;
    this.activeConversationId = conversationId;
  }

  private startRenameConversation(id: string, currentTitle: string | null, e: Event) {
    e.stopPropagation();
    this.editingConversationId = id;
    this.editingConversationTitle = currentTitle ?? '';
    this.updateComplete.then(() => {
      const input = this.shadowRoot?.querySelector('.rename-conv-input') as HTMLInputElement | null;
      input?.focus();
      input?.select();
    });
  }

  private async commitConversationRename() {
    if (!this.editingConversationId) return;
    const title = this.editingConversationTitle.trim();
    if (title) {
      try {
        await this.client.updateConversation(this.editingConversationId, title);
        await this.refreshConversations();
      } catch (err) {
        console.error('Failed to rename conversation:', err);
      }
    }
    this.editingConversationId = null;
    this.editingConversationTitle = '';
  }

  private handleConversationRenameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      this.commitConversationRename();
    } else if (e.key === 'Escape') {
      this.editingConversationId = null;
      this.editingConversationTitle = '';
    }
  }

  private async handleDeleteConversation(id: string, e: Event) {
    e.stopPropagation();
    try {
      await this.client.deleteConversation(id);
      if (this.activeConversationId === id) {
        this.activeConversationId = null;
        this.sessionId = null;
        this.messages = [];
      }
      this.memorizedConversationIds.delete(id);
      this.memorizedConversationIds = new Set(this.memorizedConversationIds);
      await this.refreshConversations();
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  }

  /* ── Conversation Memory ────────────────────────────────── */

  private async refreshMemories() {
    try {
      this.memories = await this.client.listMemories();
      this.memorizedConversationIds = new Set(this.memories.map(m => m.conversation_id));
    } catch (err) {
      console.error('Failed to load memories:', err);
    }
  }

  /** @deprecated alias kept for call-sites */
  private refreshMemorizedIds() { return this.refreshMemories(); }

  private async handleMemorize(conversationId: string, e: Event) {
    e.stopPropagation();
    if (this.memorizingConversationId) return; // one at a time
    this.memorizingConversationId = conversationId;
    try {
      await this.client.createMemory(conversationId);
      await this.refreshMemories();
    } catch (err) {
      console.error('Failed to memorize conversation:', err);
    } finally {
      this.memorizingConversationId = null;
    }
  }

  private handleMemorySearchInput(e: InputEvent) {
    this.memorySearchQuery = (e.target as HTMLInputElement).value;
    if (!this.memorySearchQuery.trim()) {
      this.memorySearchResults = [];
    }
  }

  private async executeMemorySearch() {
    const query = this.memorySearchQuery.trim();
    if (!query) return;
    this.memorySearchLoading = true;
    try {
      const result = await this.client.searchMemories(query, 10);
      this.memorySearchResults = result.results;
    } catch (err) {
      console.error('Memory search failed:', err);
      this.memorySearchResults = [];
    } finally {
      this.memorySearchLoading = false;
    }
  }

  private handleMemorySearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      this.executeMemorySearch();
    }
  }

  private handleSearchResultClick(conversationId: string) {
    // Find the memory for this conversation and show its detail
    const mem = this.memories.find(m => m.conversation_id === conversationId);
    if (mem) {
      this.handleSelectMemory(mem);
    } else {
      this.handleSelectConversation(conversationId);
    }
  }

  private handleSelectMemory(mem: MemorySummary) {
    this.selectedMemory = mem;
    // Deselect conversation/session views so the main area shows the memory detail
    this.sessionId = null;
    this.activeConversationId = null;
    this.messages = [];
  }

  private handleBackFromMemory() {
    this.selectedMemory = null;
  }

  private handleViewConversationFromMemory(conversationId: string) {
    this.selectedMemory = null;
    this.handleSelectConversation(conversationId);
  }

  private async handleDeleteMemory(conversationId: string, e?: Event) {
    e?.stopPropagation();
    try {
      await this.client.deleteMemory(conversationId);
      if (this.selectedMemory?.conversation_id === conversationId) {
        this.selectedMemory = null;
      }
      await this.refreshMemories();
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  }

  /* ── User Profile Memory ────────────────────────────────── */

  private async fetchProfile() {
    try {
      this.userProfile = await this.client.getProfile();
    } catch (err) {
      console.error('Failed to fetch profile:', err);
    }
  }

  private showProfileToast(msg: string) {
    this.profileToast = msg;
    setTimeout(() => { this.profileToast = null; }, 4000);
  }

  private toggleProfileDrawer() {
    this.profileDrawerOpen = !this.profileDrawerOpen;
  }

  private async handleGenerateProfileFromAll() {
    if (this.profileGenerating) return;
    this.profileGenerating = true;
    try {
      const result = await this.client.generateProfileFromAll(20);
      this.userProfile = result.profile;
      this.profileDrawerOpen = true;
      this.showProfileToast(
        result.profile_changed
          ? result.change_summary
          : 'No new personal information found',
      );
    } catch (err) {
      console.error('Failed to generate profile:', err);
      this.showProfileToast('Failed to generate profile');
    } finally {
      this.profileGenerating = false;
    }
  }

  private async handleGenerateProfileFromConversation(conversationId: string, e?: Event) {
    e?.stopPropagation();
    if (this.profileGenerating) return;
    this.profileGenerating = true;
    try {
      const result = await this.client.generateProfile(conversationId);
      this.userProfile = result.profile;
      this.showProfileToast(
        result.profile_changed
          ? result.change_summary
          : 'No new personal info found',
      );
    } catch (err) {
      console.error('Failed to generate profile:', err);
      this.showProfileToast('Failed to update profile');
    } finally {
      this.profileGenerating = false;
    }
  }

  private async handleDeleteProfile() {
    try {
      await this.client.deleteProfile();
      this.userProfile = null;
      this.profileDrawerOpen = false;
      this.showProfileToast('Profile deleted');
    } catch (err) {
      console.error('Failed to delete profile:', err);
    }
  }

  /* ── Prompt modal ────────────────────────────────────────── */

  private async togglePromptModal() {
    if (this.promptModalOpen) {
      this.promptModalOpen = false;
      return;
    }
    this.promptModalOpen = true;
    if (this.promptContent === null) {
      this.promptLoading = true;
      try {
        const data = await this.client.getPrompt('customer_support');
        this.promptContent = data.content;
      } catch (err) {
        console.error('Failed to fetch prompt:', err);
        this.promptContent = 'Failed to load prompt.';
      } finally {
        this.promptLoading = false;
      }
    }
  }

  private async handleCopyPrompt() {
    if (!this.promptContent) return;
    await navigator.clipboard.writeText(this.promptContent);
    this.promptCopied = true;
    setTimeout(() => { this.promptCopied = false; }, 2000);
  }

  /* ── Chat flow ──────────────────────────────────────────── */

  private async send(text: string) {
    if (!text.trim() || this.isLoading) return;

    // If viewing a conversation from history, resume it as a live session
    if (this.activeConversationId && !this.sessionId) {
      this.resumeConversation(this.activeConversationId);
    }

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      toolCalls: [],
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      toolCalls: [],
      isStreaming: true,
    };
    this.messages = [...this.messages, userMsg, assistantMsg];
    this.isLoading = true;
    this.scrollToBottom();

    const toolCalls = new Map<string, ToolCallInfo>();

    const updateAssistant = (patch: Partial<ChatMessage>) => {
      this.messages = this.messages.map(m =>
        m.id === assistantId ? { ...m, ...patch } : m,
      );
    };

    try {
      const result = await this.client.sendMessage(text, this.sessionId, {
        onTextContent: (delta) => {
          const cur = this.messages.find(m => m.id === assistantId)!;
          updateAssistant({ content: cur.content + delta });
          this.scrollToBottom();
        },

        onToolCallStart: (id, name) => {
          toolCalls.set(id, { id, name, status: 'running' });
          updateAssistant({ toolCalls: Array.from(toolCalls.values()) });
          this.scrollToBottom();
        },

        onToolCallResult: (id, res) => {
          const tc = toolCalls.get(id);
          if (tc) {
            tc.result = res;

            // ★ Convert tool result → A2UI messages & build surface
            const surfaceId = `tool-${id}`;
            const a2uiMsgs = convertToolResult(tc.name, res, surfaceId)
              ?? convertGenericResult(tc.name, res, surfaceId);

            const processor = new A2UIProcessor();
            processor.processMessages(a2uiMsgs);
            const readySurfaces = processor.getReadySurfaces();
            const surface = readySurfaces.get(surfaceId);

            if (surface) {
              tc.surface = surface;
              tc.surfaceId = surfaceId;
            }
          }
        },

        onToolCallEnd: (id) => {
          const tc = toolCalls.get(id);
          if (tc) {
            tc.status = 'completed';
            updateAssistant({ toolCalls: Array.from(toolCalls.values()) });
          }
          this.scrollToBottom();
        },

        onError: (msg) => {
          updateAssistant({ content: `Error: ${msg}`, isStreaming: false });
        },

        onFinished: () => {
          updateAssistant({ isStreaming: false });
        },
      });

      if (result.sessionId && !this.sessionId) this.sessionId = result.sessionId;
      // Refresh session and conversation lists
      this.refreshSessions();
      this.refreshConversations();
    } catch (err) {
      console.error(err);
      updateAssistant({ content: 'Sorry, an error occurred. Please try again.', isStreaming: false });
    } finally {
      this.isLoading = false;
      this.inputEl?.focus();
    }
  }

  private handleSubmit(e: Event) {
    e.preventDefault();
    if (!this.inputEl) return;
    const text = this.inputEl.value.trim();
    if (text) {
      this.inputEl.value = '';
      this.send(text);
    }
  }

  private handleSuggestion(text: string) {
    this.send(text);
  }

  /* ── Render ─────────────────────────────────────────────── */

  render() {
    return html`
      ${this.promptModalOpen ? this.renderPromptModal() : nothing}
      ${this.renderSidebar()}
      <div class="main">
        ${this.renderHeader()}
        ${this.selectedMemory
          ? this.renderMemoryDetail(this.selectedMemory)
          : html`
            <div class="messages-area">
              <div class="messages-container">
                ${this.messages.length === 0
                  ? this.renderWelcome()
                  : repeat(this.messages, m => m.id, m => this.renderMessage(m))}
              </div>
            </div>
            ${this.renderInput()}
          `}
      </div>
    `;
  }

  /* ── Sidebar ────────────────────────────────────────────── */

  private renderSidebar() {
    return html`
      <aside class="sidebar ${this.sidebarOpen ? '' : 'collapsed'}">
        <div class="sidebar-header">
          <h2>Chat</h2>
          <div class="sidebar-actions">
            <button class="icon-btn" title="New session" @click=${this.handleCreateSession}>
              <span class="material-symbols-outlined" style="font-size:20px">add</span>
            </button>
            <button class="icon-btn" title="Collapse sidebar" @click=${this.toggleSidebar}>
              <span class="material-symbols-outlined" style="font-size:20px">close</span>
            </button>
          </div>
        </div>
        <div class="session-list">
          <!-- Active Sessions -->
          <div class="sidebar-section-header">
            <h3>Sessions</h3>
            <hr />
          </div>
          ${this.sessions.length === 0
            ? html`<div class="no-conversations">No active sessions</div>`
            : repeat(this.sessions, s => s.session_id, s => this.renderSessionItem(s))}

          <!-- Conversation History -->
          <div class="sidebar-section-header">
            <h3>History</h3>
            <hr />
          </div>
          ${this.conversations.length === 0
            ? html`<div class="no-conversations">No conversations yet</div>`
            : repeat(this.conversations, c => c.id, c => this.renderConversationItem(c))}

          <!-- Memory -->
          <div class="sidebar-section-header">
            <h3>Memory</h3>
            <hr />
          </div>
          <div class="memory-search-wrapper">
            <input
              class="memory-search-input"
              type="text"
              placeholder="Search memories..."
              .value=${this.memorySearchQuery}
              @input=${this.handleMemorySearchInput}
              @keydown=${this.handleMemorySearchKeydown}
            />
          </div>
          ${this.memorySearchLoading
            ? html`<div class="no-conversations">Searching...</div>`
            : this.memorySearchQuery.trim() && this.memorySearchResults.length > 0
              ? this.memorySearchResults.map(r => html`
                <div class="memory-result-item" @click=${() => this.handleSearchResultClick(r.conversation_id)}>
                  <div class="memory-result-summary">${r.summary}</div>
                  <div class="memory-result-meta">
                    ${r.source_title ?? 'Untitled'}
                    <span class="memory-badge">${(r.similarity * 100).toFixed(0)}%</span>
                  </div>
                </div>
              `)
              : this.memorySearchQuery.trim()
                ? html`<div class="no-conversations">No results</div>`
                : this.memories.length === 0
                  ? html`<div class="no-conversations">No memories yet</div>`
                  : this.memories.map(m => this.renderMemoryItem(m))}
        </div>
        ${this.profileDrawerOpen ? this.renderProfileDrawer() : nothing}
        ${this.currentUser
          ? html`
            <div class="user-card" @click=${this.toggleProfileDrawer}>
              <div class="user-avatar">${this.currentUser.initials}</div>
              <div class="user-meta">
                <div class="user-name">${this.currentUser.display_name}</div>
                ${this.buildId ? html`<div class="build-id">Build ${this.buildId}</div>` : nothing}
              </div>
              <span class="material-symbols-outlined" style="font-size:16px; margin-left:auto; color: light-dark(var(--n-60), var(--n-50))">
                ${this.profileDrawerOpen ? 'expand_more' : 'expand_less'}
              </span>
            </div>
          `
          : nothing}
        ${!this.currentUser && this.buildId
          ? html`<div class="sidebar-build-id">Build ${this.buildId}</div>`
          : nothing}
      </aside>
      ${this.profileToast
        ? html`<div class="profile-toast">${this.profileToast}</div>`
        : nothing}
    `;
  }

  private renderConversationItem(c: ConversationSummary) {
    const isActive = c.id === this.activeConversationId;
    const isEditing = c.id === this.editingConversationId;
    const displayTitle = c.title || `Chat ${c.id.slice(0, 8)}`;

    return html`
      <div
        class="session-item ${isActive ? 'active' : ''}"
        @click=${() => this.handleSelectConversation(c.id)}
      >
        <span class="session-icon material-symbols-outlined" style="font-size:18px">history</span>
        ${isEditing
          ? html`
            <input
              class="rename-input rename-conv-input"
              .value=${this.editingConversationTitle}
              @input=${(e: InputEvent) => this.editingConversationTitle = (e.target as HTMLInputElement).value}
              @keydown=${this.handleConversationRenameKeydown}
              @blur=${this.commitConversationRename}
              @click=${(e: Event) => e.stopPropagation()}
            />
          `
          : html`
            <div class="session-info">
              <div class="session-title">${displayTitle}</div>
              <div class="session-meta">${c.message_count} msgs · ${this.formatDate(c.updated_at)}</div>
            </div>
          `}
        <div class="session-item-actions">
          <button class="icon-btn" title="Rename"
            @click=${(e: Event) => this.startRenameConversation(c.id, c.title, e)}>
            <span class="material-symbols-outlined">edit</span>
          </button>
          <button class="icon-btn"
            title=${this.memorizedConversationIds.has(c.id) ? 'Re-memorize' : 'Memorize'}
            @click=${(e: Event) => this.handleMemorize(c.id, e)}
            ?disabled=${this.memorizingConversationId === c.id}>
            ${this.memorizingConversationId === c.id
              ? html`<div class="mini-spinner"></div>`
              : html`<span class="material-symbols-outlined"
                  style="color: ${this.memorizedConversationIds.has(c.id) ? 'light-dark(#0369a1, #7dd3fc)' : 'inherit'}">
                  ${this.memorizedConversationIds.has(c.id) ? 'psychology_alt' : 'psychology'}
                </span>`}
          </button>
          <button class="icon-btn" title="Delete"
            @click=${(e: Event) => this.handleDeleteConversation(c.id, e)}>
            <span class="material-symbols-outlined">delete</span>
          </button>
        </div>
      </div>
    `;
  }

  private renderSessionItem(s: SessionInfo) {
    const isActive = s.session_id === this.sessionId;
    const isEditing = s.session_id === this.editingSessionId;
    const displayTitle = s.title || `Chat ${s.session_id.slice(0, 8)}`;

    return html`
      <div
        class="session-item ${isActive ? 'active' : ''}"
        @click=${() => this.handleSelectSession(s.session_id)}
      >
        <span class="session-icon material-symbols-outlined" style="font-size:18px">chat_bubble</span>
        ${isEditing
          ? html`
            <input
              class="rename-input"
              .value=${this.editingTitle}
              @input=${(e: InputEvent) => this.editingTitle = (e.target as HTMLInputElement).value}
              @keydown=${this.handleRenameKeydown}
              @blur=${this.commitRename}
              @click=${(e: Event) => e.stopPropagation()}
            />
          `
          : html`
            <div class="session-info">
              <div class="session-title">${displayTitle}</div>
              <div class="session-meta">${s.message_count} msgs · ${this.formatDate(s.last_activity)}</div>
            </div>
          `}
        <div class="session-item-actions">
          <button class="icon-btn" title="Rename"
            @click=${(e: Event) => this.startRenameSession(s.session_id, s.title, e)}>
            <span class="material-symbols-outlined">edit</span>
          </button>
          <button class="icon-btn" title="Delete"
            @click=${(e: Event) => this.handleDeleteSession(s.session_id, e)}>
            <span class="material-symbols-outlined">delete</span>
          </button>
        </div>
      </div>
    `;
  }

  private renderHeader() {
    return html`
      <header>
        <div class="header-left">
          ${!this.sidebarOpen
            ? html`<button class="icon-btn" title="Open sidebar" @click=${this.toggleSidebar}>
                <span class="material-symbols-outlined" style="font-size:20px">menu</span>
              </button>`
            : nothing}
          <div class="logo">
            <span class="material-symbols-outlined" style="font-size:18px">auto_awesome</span>
          </div>
          <div class="title">
            <h1>Customer Support</h1>
          </div>
        </div>
        <div class="header-actions">
          ${this.sessionId
            ? html`<button class="hdr-btn" @click=${this.newChat}>New Chat</button>`
            : nothing}
          <button class="icon-btn" @click=${this.togglePromptModal} title="View system prompt">
            <span class="material-symbols-outlined" style="font-size:18px">info</span>
          </button>
          <button class="icon-btn" @click=${this.toggleTheme} title="Toggle theme">
            <span class="material-symbols-outlined" style="font-size:18px">dark_mode</span>
          </button>
        </div>
      </header>
    `;
  }

  private renderWelcome() {
    const suggestions = [
      { text: 'What is the status of order ORD-001?', icon: 'local_shipping' },
      { text: 'Check order ORD-002', icon: 'package_2' },
      { text: 'Where is my package ORD-003?', icon: 'help' },
    ];
    return html`
      <div class="welcome">
        <div class="welcome-logo">
          <span class="material-symbols-outlined" style="font-size:24px">auto_awesome</span>
        </div>
        <h2>How can I help you today?</h2>
        <p>I can help you check order status and answer questions about your purchases.</p>
        <div class="suggestions">
          ${suggestions.map(s => html`
            <button class="sug-btn" @click=${() => this.handleSuggestion(s.text)}>
              <span class="material-symbols-outlined">${s.icon}</span>
              ${s.text}
            </button>
          `)}
        </div>
      </div>
    `;
  }

  private renderMessage(msg: ChatMessage) {
    return html`
      <div class="msg ${msg.role}">
        <div class="avatar ${msg.role}">
          <span class="material-symbols-outlined" style="font-size:16px">
            ${msg.role === 'user' ? 'account_circle' : 'auto_awesome'}
          </span>
        </div>
        <div class="msg-body">
          <div class="msg-role">${msg.role === 'user' ? 'You' : 'Assistant'}</div>

          <!-- Tool calls (rendered as A2UI surfaces) -->
          ${msg.toolCalls.map(tc => this.renderToolCall(tc))}

          <!-- Text content -->
          ${msg.content || msg.isStreaming
            ? html`<div class="bubble">
                ${msg.role === 'assistant'
                  ? unsafeHTML(this.parseMarkdown(msg.content))
                  : msg.content}${msg.isStreaming && !msg.content
                  ? html`<div class="loading-dots"><span></span><span></span><span></span></div>`
                  : msg.isStreaming
                    ? html`<span class="cursor"></span>`
                    : nothing}
              </div>`
            : nothing}
        </div>
      </div>
    `;
  }

  private renderToolCall(tc: ToolCallInfo) {
    // While running, show indicator
    if (tc.status === 'running') {
      return html`
        <div class="tool-indicator">
          <div class="spinner"></div>
          <span>Calling</span>
          <span class="tool-name">${tc.name}</span>
        </div>
      `;
    }

    // Completed: if we have a surface, render it natively via <a2ui-surface>
    if (tc.surface) {
      return html`
        <div class="surface-wrapper">
          <a2ui-surface .surface=${tc.surface} .surfaceId=${tc.surfaceId ?? ''}></a2ui-surface>
        </div>
      `;
    }

    // Fallback: show raw result
    return html`
      <div class="tool-indicator">
        <span class="material-symbols-outlined">check_circle</span>
        <span class="tool-name">${tc.name}</span>
        <span>${tc.result ?? ''}</span>
      </div>
    `;
  }

  private renderMemoryItem(m: MemorySummary) {
    const isActive = this.selectedMemory?.conversation_id === m.conversation_id;
    const title = m.source_title || 'Untitled';
    const preview = m.summary.length > 60 ? m.summary.slice(0, 60) + '…' : m.summary;
    return html`
      <div class="memory-item ${isActive ? 'active' : ''}" @click=${() => this.handleSelectMemory(m)}>
        <span class="memory-item-icon material-symbols-outlined" style="font-size:18px">psychology_alt</span>
        <div class="memory-item-info">
          <div class="memory-item-title">${title}</div>
          <div class="memory-item-preview">${preview}</div>
        </div>
        <div class="memory-item-actions">
          <button class="icon-btn" title="Delete memory"
            @click=${(e: Event) => this.handleDeleteMemory(m.conversation_id, e)}>
            <span class="material-symbols-outlined">delete</span>
          </button>
        </div>
      </div>
    `;
  }

  private renderMemoryDetail(m: MemorySummary) {
    const created = new Date(m.created_at);
    const updated = new Date(m.updated_at);
    const fmt = (d: Date) =>
      d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) +
      ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

    return html`
      <div class="messages-area">
        <div class="memory-detail">
          <div class="memory-detail-header">
            <div class="memory-detail-icon">
              <span class="material-symbols-outlined" style="font-size:22px">psychology_alt</span>
            </div>
            <div class="memory-detail-title">
              <h2>${m.source_title || 'Untitled Memory'}</h2>
              <p>${m.message_count} messages · memorized ${this.formatDate(m.created_at)}</p>
            </div>
          </div>

          <div class="memory-detail-section">
            <h3>Summary</h3>
            <div class="memory-detail-summary">${m.summary}</div>
          </div>

          <div class="memory-detail-section">
            <h3>Metadata</h3>
            <dl class="memory-detail-meta">
              <dt>Conversation ID</dt>
              <dd>${m.conversation_id}</dd>
              <dt>User ID</dt>
              <dd>${m.user_id}</dd>
              <dt>Messages</dt>
              <dd>${m.message_count}</dd>
              <dt>Created</dt>
              <dd>${fmt(created)}</dd>
              <dt>Updated</dt>
              <dd>${fmt(updated)}</dd>
            </dl>
          </div>

          <div class="memory-detail-actions">
            <button @click=${this.handleBackFromMemory}>
              <span class="material-symbols-outlined" style="font-size:16px">arrow_back</span>
              Back
            </button>
            <button @click=${() => this.handleViewConversationFromMemory(m.conversation_id)}>
              <span class="material-symbols-outlined" style="font-size:16px">chat</span>
              View conversation
            </button>
            <button @click=${() => this.handleDeleteMemory(m.conversation_id)}>
              <span class="material-symbols-outlined" style="font-size:16px">delete</span>
              Delete memory
            </button>
          </div>
        </div>
      </div>
    `;
  }

  /* ── Profile Drawer ─────────────────────────────────────── */

  private renderProfileDrawer() {
    const p = this.userProfile;

    return html`
      <div class="profile-drawer">
        <div class="profile-drawer-header">
          <h3>User Profile</h3>
          <button class="icon-btn" @click=${(e: Event) => { e.stopPropagation(); this.profileDrawerOpen = false; }}>
            <span class="material-symbols-outlined" style="font-size:18px">close</span>
          </button>
        </div>
        ${p
          ? this.renderProfileContent(p)
          : this.renderProfileEmpty()}
      </div>
    `;
  }

  private renderProfileEmpty() {
    return html`
      <div class="profile-drawer-body">
        <div class="profile-empty">
          <span class="material-symbols-outlined">person_off</span>
          No profile yet.
          <br/>Generate one from your conversations.
          <br/>
          <button
            class="profile-gen-btn"
            @click=${(e: Event) => { e.stopPropagation(); this.handleGenerateProfileFromAll(); }}
            ?disabled=${this.profileGenerating}
          >
            ${this.profileGenerating
              ? html`<div class="mini-spinner"></div> Generating...`
              : html`<span class="material-symbols-outlined" style="font-size:16px">person_add</span> Generate Profile`}
          </button>
        </div>
      </div>
    `;
  }

  private renderProfileContent(p: UserProfile) {
    const hasBasicInfo = Object.keys(p.basic_info).length > 0;
    const hasInterests = p.interests.length > 0;
    const hasHabits = p.habits.length > 0;
    const hasPreferences = Object.keys(p.preferences).length > 0;
    const hasStatus = Object.keys(p.status).some(k => p.status[k]);
    const hasFacts = p.facts.length > 0;

    return html`
      <div class="profile-drawer-body">
        ${hasBasicInfo ? html`
          <div class="profile-section">
            <h4>Basic Info</h4>
            <dl class="profile-kv">
              ${Object.entries(p.basic_info)
                .filter(([, v]) => v)
                .map(([k, v]) => html`
                  <dt>${this.formatKey(k)}</dt>
                  <dd>${v}</dd>
                `)}
            </dl>
          </div>
        ` : nothing}

        ${hasInterests ? html`
          <div class="profile-section">
            <h4>Interests</h4>
            <div class="profile-tags">
              ${p.interests.map(i => html`<span class="profile-tag">${i}</span>`)}
            </div>
          </div>
        ` : nothing}

        ${hasHabits ? html`
          <div class="profile-section">
            <h4>Habits</h4>
            <ul class="profile-list">
              ${p.habits.map(h => html`<li>${h}</li>`)}
            </ul>
          </div>
        ` : nothing}

        ${hasPreferences ? html`
          <div class="profile-section">
            <h4>Preferences</h4>
            <dl class="profile-kv">
              ${Object.entries(p.preferences)
                .filter(([, v]) => v)
                .map(([k, v]) => html`
                  <dt>${this.formatKey(k)}</dt>
                  <dd>${v}</dd>
                `)}
            </dl>
          </div>
        ` : nothing}

        ${hasStatus ? html`
          <div class="profile-section">
            <h4>Status</h4>
            <dl class="profile-kv">
              ${Object.entries(p.status)
                .filter(([, v]) => v)
                .map(([k, v]) => html`
                  <dt>${this.formatKey(k)}</dt>
                  <dd>${v}</dd>
                `)}
            </dl>
          </div>
        ` : nothing}

        ${hasFacts ? html`
          <div class="profile-section">
            <h4>Notable Facts</h4>
            <ul class="profile-list">
              ${p.facts.map(f => html`<li>${f}</li>`)}
            </ul>
          </div>
        ` : nothing}

        ${!hasBasicInfo && !hasInterests && !hasHabits && !hasPreferences && !hasStatus && !hasFacts
          ? html`<div class="profile-empty">
              <span class="material-symbols-outlined">info</span>
              Profile exists but has no data yet.
            </div>`
          : nothing}
      </div>

      <div class="profile-footer">
        <span>v${p.version} · updated ${this.formatDate(p.updated_at)}</span>
        <div class="profile-footer-actions">
          <button
            class="icon-btn"
            title="Update profile from all conversations"
            @click=${(e: Event) => { e.stopPropagation(); this.handleGenerateProfileFromAll(); }}
            ?disabled=${this.profileGenerating}
          >
            ${this.profileGenerating
              ? html`<div class="mini-spinner"></div>`
              : html`<span class="material-symbols-outlined" style="font-size:16px">refresh</span>`}
          </button>
          <button class="icon-btn" title="Delete profile"
            @click=${(e: Event) => { e.stopPropagation(); this.handleDeleteProfile(); }}>
            <span class="material-symbols-outlined" style="font-size:16px">delete</span>
          </button>
        </div>
      </div>
    `;
  }

  private formatKey(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  /* ── Prompt Modal ─────────────────────────────────────────── */

  private renderPromptModal() {
    return html`
      <div class="prompt-overlay" @click=${this.togglePromptModal}>
        <div class="prompt-card" @click=${(e: Event) => e.stopPropagation()}>
          <div class="prompt-card-header">
            <h3>
              <span class="material-symbols-outlined" style="font-size:18px">info</span>
              System Prompt
            </h3>
            <div class="prompt-header-actions">
              <button
                class="prompt-copy-btn ${this.promptCopied ? 'copied' : ''}"
                @click=${this.handleCopyPrompt}
                ?disabled=${this.promptLoading || !this.promptContent}
              >
                <span class="material-symbols-outlined" style="font-size:15px">
                  ${this.promptCopied ? 'check' : 'content_copy'}
                </span>
                ${this.promptCopied ? 'Copied' : 'Copy'}
              </button>
              <button class="icon-btn" @click=${this.togglePromptModal}>
                <span class="material-symbols-outlined" style="font-size:18px">close</span>
              </button>
            </div>
          </div>
          <div class="prompt-card-body">
            ${this.promptLoading
              ? html`<div class="prompt-loading">
                  <div class="spinner" style="width:16px;height:16px;border:2px solid light-dark(var(--n-80),var(--n-30));border-left-color:light-dark(var(--n-40),var(--n-70));border-radius:50%;animation:spin .8s linear infinite"></div>
                  Loading…
                </div>`
              : html`<pre class="prompt-code">${this.promptContent}</pre>`}
          </div>
        </div>
      </div>
    `;
  }

  private renderInput() {
    return html`
      <div class="input-area">
        <form class="input-row" @submit=${this.handleSubmit}>
          <input
            id="msg-input"
            type="text"
            placeholder="Type your message..."
            autocomplete="off"
            ?disabled=${this.isLoading}
          />
          <button class="send-btn" type="submit" ?disabled=${this.isLoading}>
            <span class="material-symbols-outlined" style="font-size:22px">send</span>
          </button>
        </form>
        <div class="input-footer">Powered by A2UI — tool results rendered as interactive surfaces</div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'a2ui-native-app': NativeApp;
  }
}
