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
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wide flex items-center gap-1.5">
            <img src={icons.documentIcon} alt="" className="w-10 h-10" /> Shared Document
          </h2>
          {versions.length > 0 && (
            <span className="text-xs text-gray-500">
              v{isLatest ? versions.length : selectedVersion}
              {isLatest && ' (latest)'}
            </span>
          )}
        </div>
      </div>

      {/* Version selector */}
      {versions.length > 1 && (
        <div className="px-4 py-2 border-b border-gray-100 bg-white">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 flex-shrink-0">Version:</span>
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => onSelectVersion(null)}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                  isLatest
                    ? 'bg-purple-100 text-purple-700 font-medium'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
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
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
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
          <div className="text-center text-gray-400 text-sm mt-8">
            <p>Document is empty</p>
            <p className="text-xs mt-1">Agents will write their findings here</p>
          </div>
        ) : (
          <div className="text-sm text-gray-700 markdown-content">
            <ReactMarkdown>{displayContent}</ReactMarkdown>
          </div>
        )}
      </div>

      {/* Version history */}
      {versions.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 max-h-28 overflow-y-auto panel-scroll">
          <div className="text-[10px] font-medium text-gray-500 uppercase mb-1">Change Log</div>
          {[...versions].reverse().map(v => {
            const colors = AGENT_COLORS[v.author] || AGENT_COLORS.facilitator;
            return (
              <div key={v.version} className="flex items-center gap-1.5 py-0.5 text-[10px] text-gray-500">
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
