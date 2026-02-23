import ReactMarkdown from 'react-markdown';
import type { DocumentVersion } from '../types';
import { AGENT_COLORS } from '../types';
import { icons } from './icons';

interface DocumentViewerProps {
  content: string;
  versions: DocumentVersion[];
  selectedVersion: number | null;
  onSelectVersion: (version: number | null) => void;
}

export default function DocumentViewer({ content, versions, selectedVersion, onSelectVersion }: DocumentViewerProps) {
  // Determine what content to show
  const displayContent = selectedVersion !== null
    ? versions.find(v => v.version === selectedVersion)?.content || ''
    : content;

  const isLatest = selectedVersion === null;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 h-[52px] flex items-center border-b border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10">
        <div className="flex items-center justify-between w-full">
          <h2 className="text-[11px] font-semibold text-n-50 dark:text-n-60 uppercase tracking-[0.06em] flex items-center gap-1.5">
            <img src={icons.documentIcon} alt="" className="w-8 h-8" /> Shared Document
          </h2>
          {versions.length > 0 && (
            <span className="text-xs text-n-60 dark:text-n-50">
              v{isLatest ? versions.length : selectedVersion}
              {isLatest && ' (latest)'}
            </span>
          )}
        </div>
      </div>

      {/* Version selector */}
      {versions.length > 1 && (
        <div className="px-4 py-2 border-b border-n-95 dark:border-n-25 bg-n-100 dark:bg-n-15">
          <div className="flex items-center gap-2">
            <span className="text-xs text-n-60 dark:text-n-50 flex-shrink-0">Version:</span>
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => onSelectVersion(null)}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                  isLatest
                    ? 'bg-p-90 dark:bg-p-30 text-p-30 dark:text-p-90 font-medium'
                    : 'bg-n-95 dark:bg-n-20 text-n-50 dark:text-n-60 hover:bg-n-90 dark:hover:bg-n-25'
                }`}
              >
                Latest
              </button>
              {versions.map(v => {
                const colors = AGENT_COLORS[v.author] || AGENT_COLORS.facilitator;
                return (
                  <button
                    key={v.version}
                    onClick={() => onSelectVersion(v.version)}
                    title={v.change_description}
                    className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                      selectedVersion === v.version
                        ? `${colors.bg} ${colors.text} font-medium`
                        : 'bg-n-95 dark:bg-n-20 text-n-50 dark:text-n-60 hover:bg-n-90 dark:hover:bg-n-25'
                    }`}
                  >
                    v{v.version}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Document content */}
      <div className="flex-1 overflow-y-auto panel-scroll p-4">
        {!displayContent ? (
          <div className="text-center text-n-60 dark:text-n-50 text-sm mt-8">
            <p>Document is empty</p>
            <p className="text-xs mt-1 text-n-70 dark:text-n-40">Agents will write their findings here</p>
          </div>
        ) : (
          <div className="text-sm text-n-10 dark:text-n-90 markdown-content">
            <ReactMarkdown>{displayContent}</ReactMarkdown>
          </div>
        )}
      </div>

      {/* Version history */}
      {versions.length > 0 && (
        <div className="px-4 py-2 border-t border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10 max-h-28 overflow-y-auto panel-scroll">
          <div className="text-[10px] font-medium text-n-50 dark:text-n-60 uppercase mb-1">Change Log</div>
          {[...versions].reverse().map(v => {
            const colors = AGENT_COLORS[v.author] || AGENT_COLORS.facilitator;
            return (
              <div key={v.version} className="flex items-center gap-1.5 py-0.5 text-[10px] text-n-60 dark:text-n-50">
                <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
                <span className="font-medium">v{v.version}</span>
                <span>{v.change_description}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
