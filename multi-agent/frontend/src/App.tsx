import { useState, useCallback } from 'react';
import type { WorkflowState } from './types';
import { useEventStream } from './hooks/useEventStream';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import TaskBoard from './components/TaskBoard';
import DocumentViewer from './components/DocumentViewer';
import AgentTimeline from './components/AgentTimeline';

const INITIAL_STATE: WorkflowState = {
  status: 'idle',
  tasks: [],
  documentContent: '',
  documentVersions: [],
  selectedVersion: null,
  timeline: [],
  finalAnswer: '',
  facilitatorStream: '',
};

export default function App() {
  const [state, setState] = useState<WorkflowState>(INITIAL_STATE);

  const updater = useCallback(
    (fn: (prev: WorkflowState) => WorkflowState) => setState(fn),
    [],
  );

  const { send } = useEventStream(updater);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header />

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Chat */}
        <div className="w-[340px] flex-shrink-0 border-r border-gray-200 bg-white">
          <ChatPanel
            onSend={send}
            status={state.status}
            finalAnswer={state.finalAnswer}
            facilitatorStream={state.facilitatorStream}
          />
        </div>

        {/* Center: Agent Timeline */}
        <div className="flex-1 min-w-0 bg-white border-r border-gray-200">
          <AgentTimeline timeline={state.timeline} />
        </div>

        {/* Right: Scratchpads (stacked) */}
        <div className="w-[380px] flex-shrink-0 flex flex-col bg-white">
          {/* Task Board (top half) */}
          <div className="flex-1 border-b border-gray-200 overflow-hidden">
            <TaskBoard tasks={state.tasks} />
          </div>

          {/* Document Viewer (bottom half) */}
          <div className="flex-1 overflow-hidden">
            <DocumentViewer
              content={state.documentContent}
              versions={state.documentVersions}
              selectedVersion={state.selectedVersion}
              onSelectVersion={(v) => setState(prev => ({ ...prev, selectedVersion: v }))}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
