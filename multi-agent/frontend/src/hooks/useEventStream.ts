// useEventStream.ts — SSE hook for connecting to the multi-agent backend

import { useCallback, useRef } from 'react';
import type { TaskItem, DocumentVersion, WorkflowState } from '../types';

let _timelineId = 0;
function nextId(): string {
  return `evt-${++_timelineId}`;
}

type StateUpdater = (fn: (prev: WorkflowState) => WorkflowState) => void;

export function useEventStream(setState: StateUpdater) {
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (message: string) => {
    // Reset state for new workflow
    _timelineId = 0;
    setState(() => ({
      status: 'running',
      tasks: [],
      documentContent: '',
      documentVersions: [],
      selectedVersion: null,
      timeline: [],
      finalAnswer: '',
      facilitatorStream: '',
    }));

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') && eventType) {
            try {
              const data = JSON.parse(line.slice(6));
              handleEvent(eventType, data, setState);
            } catch {
              // Skip malformed JSON
            }
            eventType = '';
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setState(prev => ({
        ...prev,
        status: 'error',
        timeline: [...prev.timeline, {
          id: nextId(),
          timestamp: Date.now(),
          type: 'error',
          data: { message: String(err) },
        }],
      }));
    }
  }, [setState]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { send, cancel };
}

function handleEvent(type: string, data: Record<string, unknown>, setState: StateUpdater) {
  const now = Date.now();

  switch (type) {
    case 'workflow_started':
      setState(prev => ({
        ...prev,
        status: 'running',
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'workflow_started',
          data,
        }],
      }));
      break;

    case 'tasks_created':
      setState(prev => ({
        ...prev,
        tasks: [...prev.tasks, ...(data.tasks as TaskItem[])],
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'tool_call',
          agent: 'facilitator',
          data: { tool: 'create_tasks', phase: 'complete', result: `Created ${(data.tasks as TaskItem[]).length} tasks` },
        }],
      }));
      break;

    case 'task_updated': {
      const updated = data as unknown as TaskItem;
      setState(prev => ({
        ...prev,
        tasks: prev.tasks.map(t => t.id === updated.id ? { ...t, finished: updated.finished } : t),
      }));
      break;
    }

    case 'document_updated': {
      const ver = data as unknown as DocumentVersion;
      setState(prev => ({
        ...prev,
        documentContent: (ver.content as string) || prev.documentContent,
        documentVersions: [...prev.documentVersions, {
          version: ver.version,
          author: ver.author,
          timestamp: ver.timestamp,
          change_description: ver.change_description,
          content: ver.content as string,
        }],
        selectedVersion: null, // Auto-follow latest
      }));
      break;
    }

    case 'agent_started':
      setState(prev => ({
        ...prev,
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'agent_started',
          agent: data.agent as string,
          displayName: data.display_name as string,
          data,
        }],
      }));
      break;

    case 'agent_finished':
      setState(prev => ({
        ...prev,
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'agent_finished',
          agent: data.agent as string,
          displayName: data.display_name as string,
          data,
        }],
      }));
      break;

    case 'agent_message':
      setState(prev => ({
        ...prev,
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'agent_message',
          agent: data.agent as string,
          displayName: data.display_name as string,
          data,
        }],
      }));
      break;

    case 'tool_call': {
      const agent = data.agent as string;
      // Single complete event per tool call — no more start/end phases
      setState(prev => ({
        ...prev,
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'tool_call',
          agent,
          data: { ...data, phase: 'complete' },
        }],
      }));
      break;
    }

    case 'facilitator_message':
      setState(prev => ({
        ...prev,
        facilitatorStream: prev.facilitatorStream + (data.content as string) + '\n',
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'agent_message',
          agent: 'facilitator',
          displayName: 'Facilitator',
          data,
        }],
      }));
      break;

    case 'final_answer':
      setState(prev => ({
        ...prev,
        finalAnswer: data.content as string,
      }));
      break;

    case 'workflow_finished':
      setState(prev => ({
        ...prev,
        status: 'finished',
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'workflow_finished',
          data,
        }],
      }));
      break;

    case 'error':
      setState(prev => ({
        ...prev,
        status: 'error',
        timeline: [...prev.timeline, {
          id: nextId(), timestamp: now, type: 'error',
          data,
        }],
      }));
      break;
  }
}
