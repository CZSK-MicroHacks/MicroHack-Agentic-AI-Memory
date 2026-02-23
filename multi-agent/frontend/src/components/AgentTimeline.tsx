import { useEffect, useRef, useState } from 'react';
import { AGENT_COLORS, AGENT_LABELS, type TimelineEntry } from '../types';
import { icons, AGENT_ICONS } from './icons';

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
      <div className="px-3 h-[40px] flex items-center border-b border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10">
        <h2 className="text-[11px] font-semibold text-n-50 dark:text-n-60 uppercase tracking-[0.06em] flex items-center gap-1.5">
          <img src={icons.timelineIcon} alt="" className="w-6 h-6" /> Timeline
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto panel-scroll p-3 space-y-1.5">
        {timeline.length === 0 ? (
          <div className="text-center text-n-60 dark:text-n-50 text-sm mt-8">
            <p>No activity yet</p>
            <p className="text-xs mt-1 text-n-70 dark:text-n-40">Events will appear here as agents work</p>
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
  const agentIcon = AGENT_ICONS[agent];

  switch (entry.type) {
    case 'workflow_started':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-n-95 dark:bg-n-20 text-xs text-n-40 dark:text-n-70 animate-fade-in">
          <img src={icons.rocketIcon} alt="" className="w-6 h-6" />
          <span className="font-medium">Workflow started</span>
        </div>
      );

    case 'workflow_finished':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-n-95 dark:bg-n-20 text-xs text-n-40 dark:text-n-70 animate-fade-in">
          <img src={icons.finishFlagIcon} alt="" className="w-6 h-6" />
          <span className="font-medium">Workflow complete</span>
        </div>
      );

    case 'agent_started':
      return (
        <div className={`flex items-center gap-2 py-1.5 px-2 rounded-lg ${colors.bg} text-xs ${colors.text} animate-fade-in`}>
          <span className={`w-2 h-2 rounded-full animate-pulse-dot ${colors.dot}`} />
          {agentIcon && <img src={agentIcon} alt="" className="w-6 h-6" />}
          <span className="font-medium">{label}</span>
          <span className="text-n-60 dark:text-n-50">started working</span>
          {Array.isArray(entry.data.task_ids) && (
            <span className="text-n-70 dark:text-n-40 ml-auto">
              tasks: {(entry.data.task_ids as number[]).join(', ')}
            </span>
          )}
        </div>
      );

    case 'agent_finished':
      return (
        <div className={`flex items-center gap-2 py-1.5 px-2 rounded-lg ${colors.bg} text-xs ${colors.text} animate-fade-in`}>
          <img src={icons.checkmarkIcon} alt="" className="w-6 h-6" />
          {agentIcon && <img src={agentIcon} alt="" className="w-6 h-6" />}
          <span className="font-medium">{label}</span>
          <span className="text-n-60 dark:text-n-50">finished</span>
        </div>
      );

    case 'agent_message':
      return (
        <div
          className={`py-1.5 px-2 rounded-lg border ${colors.border} bg-n-100 dark:bg-n-20 cursor-pointer animate-fade-in`}
          onClick={onToggle}
        >
          <div className="flex items-center gap-2 text-xs">
            {agentIcon && <img src={agentIcon} alt="" className="w-6 h-6" />}
            <span className={`font-medium ${colors.text}`}>{label}</span>
            <img src={icons.messageIcon} alt="" className="w-5 h-5 inline" />
            <span className="text-n-70 dark:text-n-40">message</span>
            <span className="ml-auto text-n-80 dark:text-n-30">{expanded ? '▼' : '▶'}</span>
          </div>
          {expanded && (
            <div className="mt-1.5 text-xs text-n-40 dark:text-n-70 whitespace-pre-wrap border-t border-n-95 dark:border-n-25 pt-1.5">
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
          className={`py-1.5 px-2 rounded-lg text-xs border bg-n-98 dark:bg-n-20 border-n-90 dark:border-n-25 text-n-40 dark:text-n-70 animate-fade-in ${hasResult ? 'cursor-pointer' : ''}`}
          onClick={hasResult ? onToggle : undefined}
        >
          <div className="flex items-center gap-1.5">
            <img src={icons.toolIcon} alt="" className="w-6 h-6" />
            {agentIcon && <img src={agentIcon} alt="" className="w-6 h-6" />}
            <span className={`font-medium ${colors.text}`}>{label}</span>
            <span className="text-n-70 dark:text-n-40">→</span>
            <code className="bg-n-95 dark:bg-n-25 px-1 py-0.5 rounded text-[10px] font-mono">{toolName}</code>
            {hasResult ? (
              <span className="ml-auto text-n-80 dark:text-n-30">{expanded ? '▼' : '▶'}</span>
            ) : null}
          </div>
          {expanded && hasResult ? (
            <div className="mt-1 text-[10px] text-n-60 dark:text-n-50 whitespace-pre-wrap border-t border-n-95 dark:border-n-25 pt-1 max-h-32 overflow-y-auto">
              {String(entry.data.result)}
            </div>
          ) : null}
        </div>
      );
    }

    case 'error':
      return (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-red-50 dark:bg-red-950/30 text-xs text-red-700 dark:text-red-300 animate-fade-in">
          <img src={icons.warningIcon} alt="" className="w-6 h-6" />
          <span className="font-medium">Error:</span>
          <span>{entry.data.message as string}</span>
        </div>
      );

    default:
      return null;
  }
}
