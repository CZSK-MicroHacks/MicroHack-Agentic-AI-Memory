import { AGENT_COLORS, AGENT_LABELS, type TaskItem } from '../types';
import { icons, AGENT_ICONS } from './icons';

interface TaskBoardProps {
  tasks: TaskItem[];
}

export default function TaskBoard({ tasks }: TaskBoardProps) {
  const doneCount = tasks.filter(t => t.finished).length;
  const total = tasks.length;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 h-[40px] flex items-center border-b border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10 justify-between">
        <h2 className="text-[11px] font-semibold text-n-50 dark:text-n-60 uppercase tracking-[0.06em] flex items-center gap-1.5">
          <img src={icons.taskboardIcon} alt="" className="w-6 h-6" /> Tasks
        </h2>
        {total > 0 && (
          <span className="text-xs font-medium text-n-60 dark:text-n-50">
            {doneCount}/{total} done
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto panel-scroll p-3 space-y-2">
        {tasks.length === 0 ? (
          <div className="text-center text-n-60 dark:text-n-50 text-sm mt-8">
            <p>No tasks yet</p>
            <p className="text-xs mt-1 text-n-70 dark:text-n-40">The facilitator will create tasks when planning starts</p>
          </div>
        ) : (
          <>
            {/* Progress bar */}
            <div className="mb-3">
              <div className="h-2 bg-n-95 dark:bg-n-25 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all duration-500"
                  style={{ width: `${total > 0 ? (doneCount / total) * 100 : 0}%` }}
                />
              </div>
            </div>

            {tasks.map(task => {
              const colors = AGENT_COLORS[task.assigned_to] || AGENT_COLORS.facilitator;
              const label = AGENT_LABELS[task.assigned_to] || task.assigned_to;
              const agentIcon = AGENT_ICONS[task.assigned_to];
              return (
                <div
                  key={task.id}
                  className={`p-2.5 rounded-lg border transition-all duration-300 animate-fade-in ${
                    task.finished
                      ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800'
                      : 'bg-n-100 dark:bg-n-20 border-n-90 dark:border-n-25'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-base mt-0.5 flex-shrink-0">
                      <img src={task.finished ? icons.checkmarkIcon : icons.hourglassIcon} alt="" className="w-6 h-6" />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-n-20 dark:text-n-80 leading-snug">{task.text}</div>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${colors.bg} ${colors.text} inline-flex items-center gap-1`}>
                          {agentIcon && <img src={agentIcon} alt="" className="w-4 h-4" />}
                          {label}
                        </span>
                        <span className="text-[10px] text-n-60 dark:text-n-50">#{task.id}</span>
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
