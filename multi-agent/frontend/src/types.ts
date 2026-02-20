// types.ts — Shared types for the multi-agent travel planner UI

export interface TaskItem {
  id: number;
  text: string;
  assigned_to: string;
  finished: boolean;
}

export interface DocumentVersion {
  version: number;
  author: string;
  timestamp: string;
  change_description: string;
  content?: string;
}

export interface TimelineEntry {
  id: string;
  timestamp: number;
  type: 'agent_started' | 'agent_finished' | 'agent_message' | 'tool_call' | 'workflow_started' | 'workflow_finished' | 'error';
  agent?: string;
  displayName?: string;
  data: Record<string, unknown>;
}

export interface WorkflowState {
  status: 'idle' | 'running' | 'finished' | 'error';
  tasks: TaskItem[];
  documentContent: string;
  documentVersions: DocumentVersion[];
  selectedVersion: number | null;
  timeline: TimelineEntry[];
  finalAnswer: string;
  facilitatorStream: string;
}

// Agent color mapping
export const AGENT_COLORS: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  facilitator: { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-300', dot: 'bg-purple-500' },
  logistics:   { bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-300',   dot: 'bg-blue-500' },
  sightseeing: { bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-300',  dot: 'bg-green-500' },
  experience:  { bg: 'bg-amber-100',  text: 'text-amber-800',  border: 'border-amber-300',  dot: 'bg-amber-500' },
  food:        { bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-300',    dot: 'bg-red-500' },
};

export const AGENT_LABELS: Record<string, string> = {
  facilitator: '🎯 Facilitator',
  logistics:   '🚂 Logistics',
  sightseeing: '🏛️ Sightseeing',
  experience:  '🎭 Experience',
  food:        '🍺 Food & Drinks',
};
