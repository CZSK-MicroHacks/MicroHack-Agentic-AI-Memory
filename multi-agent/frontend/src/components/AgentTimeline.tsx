import { useEffect, useRef, useState } from 'react';
import { AGENT_COLORS, AGENT_LABELS, type TimelineEntry } from '../types';

interface AgentTimelineProps {
  timeline: TimelineEntry[];
}

export default function AgentTimeline({ timeline }: AgentTimelineProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [timeline.length]);

  const toggle = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">⏱️ Agent Timeline</h2>
      </div>

      <div className="flex-1 overflow-y-auto panel-scroll p-3 space-y-1.5">
        {timeline.length === 0 ? (
          <div className="text-center text-gray-400 text-sm mt-8">
            <p>No activity yet</p>
            <p className="text-xs mt-1">Events will appear here as agents work</p>
          </div>
        ) : (
          timeline.map(entry => (
            <TimelineItem
              key={entry.id}
              entry={entry}
              expanded={expandedIds.has(entry.id)}
              onToggle={() => toggle(entry.id)}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function TimelineItem({ entry, expanded, onToggle }: { entry: TimelineEntry; expanded: boolean; onToggle: () => void }) {
  const agent = entry.agent || 'facilitator';
  const colors = AGENT_COLORS[agent] || AGENT_COLORS.facilitator;
  const label = AGENT_LABELS[agent] || agent;

  switch (entry.type) {
    case 'workflow_started':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-gray-100 text-xs text-gray-600">
          <span>🚀</span>
          <span className="font-medium">Workflow started</span>
        </div>
      );

    case 'workflow_finished':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-green-100 text-xs text-green-700">
          <span>🏁</span>
          <span className="font-medium">Workflow complete</span>
        </div>
      );

    case 'agent_started':
      return (
        <div className={`flex items-center gap-2 py-1.5 px-2 rounded ${colors.bg} text-xs ${colors.text}`}>
          <span className={`w-2 h-2 rounded-full animate-pulse-dot ${colors.dot}`} />
          <span className="font-medium">{label}</span>
          <span className="text-gray-500">started working</span>
          {Array.isArray(entry.data.task_ids) && (
            <span className="text-gray-400 ml-auto">
              tasks: {(entry.data.task_ids as number[]).join(', ')}
            </span>
          )}
        </div>
      );

    case 'agent_finished':
      return (
        <div className={`flex items-center gap-2 py-1.5 px-2 rounded ${colors.bg} text-xs ${colors.text}`}>
          <span>✓</span>
          <span className="font-medium">{label}</span>
          <span className="text-gray-500">finished</span>
        </div>
      );

    case 'agent_message':
      return (
        <div
          className={`py-1.5 px-2 rounded border ${colors.border} bg-white cursor-pointer`}
          onClick={onToggle}
        >
          <div className="flex items-center gap-2 text-xs">
            <span className={`font-medium ${colors.text}`}>{label}</span>
            <span className="text-gray-400">💬 message</span>
            <span className="ml-auto text-gray-300">{expanded ? '▼' : '▶'}</span>
          </div>
          {expanded && (
            <div className="mt-1.5 text-xs text-gray-600 whitespace-pre-wrap border-t border-gray-100 pt-1.5">
              {entry.data.content as string}
            </div>
          )}
        </div>
      );

    case 'tool_call': {
      const toolName = entry.data.tool as string;
      const hasResult = !!entry.data.result;

      return (
        <div
          className={`py-1.5 px-2 rounded text-xs border bg-gray-50 border-gray-200 text-gray-600 ${hasResult ? 'cursor-pointer' : ''}`}
          onClick={hasResult ? onToggle : undefined}
        >
          <div className="flex items-center gap-1.5">
            <span>⚡</span>
            <span className={`font-medium ${colors.text}`}>{label}</span>
            <span className="text-gray-400">→</span>
            <code className="bg-gray-200 px-1 py-0.5 rounded text-[10px]">{toolName}</code>
            {hasResult ? (
              <span className="ml-auto text-gray-300">{expanded ? '▼' : '▶'}</span>
            ) : null}
          </div>
          {expanded && hasResult ? (
            <div className="mt-1 text-[10px] text-gray-500 whitespace-pre-wrap border-t border-gray-100 pt-1 max-h-32 overflow-y-auto">
              {String(entry.data.result)}
            </div>
          ) : null}
        </div>
      );
    }

    case 'error':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-red-100 text-xs text-red-700">
          <span>⚠️</span>
          <span className="font-medium">Error:</span>
          <span>{entry.data.message as string}</span>
        </div>
      );

    default:
      return null;
  }
}
