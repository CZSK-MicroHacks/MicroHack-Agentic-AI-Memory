import { useState, useCallback } from 'react';
import type { WorkflowState } from './types';
import { useEventStream } from './hooks/useEventStream';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import TaskBoard from './components/TaskBoard';
import DocumentModal from './components/DocumentModal';
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [docModalOpen, setDocModalOpen] = useState(false);

  const updater = useCallback(
    (fn: (prev: WorkflowState) => WorkflowState) => setState(fn),
    [],
  );

  const { send } = useEventStream(updater);

  const timelineInCenter = state.status === 'running';
  const timelineInSidebar = !timelineInCenter && state.timeline.length > 0;

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-n-100 dark:bg-n-15 text-n-10 dark:text-n-90">
      <Header
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(s => !s)}
        onOpenDocument={() => setDocModalOpen(true)}
        documentVersionCount={state.documentVersions.length}
      />

      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar: Tasks first, then Timeline (after processing) */}
        <aside
          className={`flex flex-col border-r border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10 overflow-hidden transition-all duration-250 ${
            sidebarOpen ? 'w-[300px] min-w-[300px]' : 'w-0 min-w-0 border-r-0'
          }`}
        >
          {/* Task Board — keeps its natural size, never shrinks */}
          <div className={`flex-shrink-0 overflow-hidden ${timelineInSidebar ? 'border-b border-n-95 dark:border-n-25' : 'flex-1'}`}>
            <TaskBoard tasks={state.tasks} />
          </div>

          {/* Timeline — takes remaining space, scrollable */}
          {timelineInSidebar && (
            <div className="flex-1 min-h-0 overflow-hidden">
              <AgentTimeline timeline={state.timeline} />
            </div>
          )}
        </aside>

        {/* Main area */}
        <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-n-100 dark:bg-n-15">
          {/* Timeline in center during processing */}
          {timelineInCenter && state.timeline.length > 0 && (
            <div className="flex-[2] min-h-0 overflow-hidden border-b border-n-95 dark:border-n-25">
              <AgentTimeline timeline={state.timeline} />
            </div>
          )}

          {/* Chat — always scrollable */}
          <div className="flex-1 min-h-0">
            <ChatPanel
              onSend={send}
              status={state.status}
              finalAnswer={state.finalAnswer}
              facilitatorStream={state.facilitatorStream}
            />
          </div>
        </main>
      </div>

      {/* Document modal */}
      <DocumentModal
        open={docModalOpen}
        onClose={() => setDocModalOpen(false)}
        content={state.documentContent}
        versions={state.documentVersions}
        selectedVersion={state.selectedVersion}
        onSelectVersion={(v) => setState(prev => ({ ...prev, selectedVersion: v }))}
      />
    </div>
  );
}
