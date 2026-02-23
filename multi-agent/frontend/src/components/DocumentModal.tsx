import ReactMarkdown from 'react-markdown';
import type { DocumentVersion } from '../types';
import { AGENT_COLORS } from '../types';
import { icons } from './icons';

interface DocumentModalProps {
  open: boolean;
  onClose: () => void;
  content: string;
  versions: DocumentVersion[];
  selectedVersion: number | null;
  onSelectVersion: (version: number | null) => void;
}

export default function DocumentModal({ open, onClose, content, versions, selectedVersion, onSelectVersion }: DocumentModalProps) {
  if (!open) return null;

  const displayContent = selectedVersion !== null
    ? versions.find(v => v.version === selectedVersion)?.content || ''
    : content;

  const isLatest = selectedVersion === null;

  return (
    <div
      className="fixed inset-0 bg-black/45 z-[900] flex items-center justify-center animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-[92%] max-w-[860px] max-h-[85vh] flex flex-col rounded-[14px] bg-n-100 dark:bg-n-15 shadow-[0_8px_30px_rgba(0,0,0,0.25)] overflow-hidden animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-n-90 dark:border-n-25">
          <h3 className="m-0 text-[15px] font-semibold text-n-10 dark:text-n-90 flex items-center gap-2">
            <img src={icons.documentIcon} alt="" className="w-6 h-6" />
            Shared Document
            {versions.length > 0 && (
              <span className="text-xs font-normal text-n-60 dark:text-n-50 ml-1">
                v{isLatest ? versions.length : selectedVersion}
                {isLatest && ' (latest)'}
              </span>
            )}
          </h3>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-md border-none bg-transparent text-n-50 dark:text-n-60 hover:bg-n-95 dark:hover:bg-n-20 hover:text-n-10 dark:hover:text-n-90 cursor-pointer transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        {/* Version selector */}
        {versions.length > 1 && (
          <div className="px-5 py-2 border-b border-n-95 dark:border-n-25 bg-n-100 dark:bg-n-15">
            <div className="flex items-center gap-2">
              <span className="text-xs text-n-60 dark:text-n-50 flex-shrink-0">Version:</span>
              <div className="flex gap-1 flex-wrap">
                <button
                  onClick={() => onSelectVersion(null)}
                  className={`text-[10px] px-2 py-0.5 rounded-full transition-colors border-none cursor-pointer ${
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
                      className={`text-[10px] px-2 py-0.5 rounded-full transition-colors border-none cursor-pointer ${
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
        <div className="flex-1 overflow-y-auto panel-scroll p-5">
          {!displayContent ? (
            <div className="text-center text-n-60 dark:text-n-50 text-sm py-10">
              <img src={icons.documentIcon} alt="" className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Document is empty</p>
              <p className="text-xs mt-1 text-n-70 dark:text-n-40">Agents will write their findings here</p>
            </div>
          ) : (
            <div className="text-sm text-n-10 dark:text-n-90 leading-relaxed markdown-content">
              <ReactMarkdown>{displayContent}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Change log footer */}
        {versions.length > 0 && (
          <div className="px-5 py-2.5 border-t border-n-95 dark:border-n-25 bg-n-98 dark:bg-n-10 max-h-32 overflow-y-auto panel-scroll">
            <div className="text-[10px] font-semibold text-n-50 dark:text-n-60 uppercase tracking-[0.06em] mb-1">Change Log</div>
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
    </div>
  );
}
