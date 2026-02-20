import { AGENT_COLORS, AGENT_LABELS, type TaskItem } from '../types';

interface TaskBoardProps {
  tasks: TaskItem[];
}

export default function TaskBoard({ tasks }: TaskBoardProps) {
  const doneCount = tasks.filter(t => t.finished).length;
  const total = tasks.length;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">📋 Task Board</h2>
        {total > 0 && (
          <span className="text-xs font-medium text-gray-500">
            {doneCount}/{total} done
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto panel-scroll p-3 space-y-2">
        {tasks.length === 0 ? (
          <div className="text-center text-gray-400 text-sm mt-8">
            <p>No tasks yet</p>
            <p className="text-xs mt-1">The facilitator will create tasks when planning starts</p>
          </div>
        ) : (
          <>
            {/* Progress bar */}
            <div className="mb-3">
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all duration-500"
                  style={{ width: `${total > 0 ? (doneCount / total) * 100 : 0}%` }}
                />
              </div>
            </div>

            {tasks.map(task => {
              const colors = AGENT_COLORS[task.assigned_to] || AGENT_COLORS.facilitator;
              const label = AGENT_LABELS[task.assigned_to] || task.assigned_to;
              return (
                <div
                  key={task.id}
                  className={`p-2.5 rounded-lg border transition-all duration-300 ${
                    task.finished
                      ? 'bg-green-50 border-green-200'
                      : 'bg-white border-gray-200'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-base mt-0.5 flex-shrink-0">
                      {task.finished ? '✅' : '⏳'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-gray-700 leading-snug">{task.text}</div>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${colors.bg} ${colors.text}`}>
                          {label}
                        </span>
                        <span className="text-[10px] text-gray-400">#{task.id}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
