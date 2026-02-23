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

// Agent color mapping — uses the neutral palette from the design system; dots keep distinct hues
export const AGENT_COLORS: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  facilitator: { bg: 'bg-n-95 dark:bg-n-20', text: 'text-n-30 dark:text-n-80', border: 'border-n-90 dark:border-n-25', dot: 'bg-p-50' },
  logistics:   { bg: 'bg-n-95 dark:bg-n-20', text: 'text-n-30 dark:text-n-80', border: 'border-n-90 dark:border-n-25', dot: 'bg-blue-500' },
  sightseeing: { bg: 'bg-n-95 dark:bg-n-20', text: 'text-n-30 dark:text-n-80', border: 'border-n-90 dark:border-n-25', dot: 'bg-green-500' },
  experience:  { bg: 'bg-n-95 dark:bg-n-20', text: 'text-n-30 dark:text-n-80', border: 'border-n-90 dark:border-n-25', dot: 'bg-amber-500' },
  food:        { bg: 'bg-n-95 dark:bg-n-20', text: 'text-n-30 dark:text-n-80', border: 'border-n-90 dark:border-n-25', dot: 'bg-red-500' },
};

export const AGENT_LABELS: Record<string, string> = {
  facilitator: 'Facilitator',
  logistics:   'Logistics',
  sightseeing: 'Sightseeing',
  experience:  'Experience',
  food:        'Food & Drinks',
};
