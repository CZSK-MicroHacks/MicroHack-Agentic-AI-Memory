import { icons } from './icons';

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onOpenDocument: () => void;
  documentVersionCount: number;
}

export default function Header({ sidebarOpen, onToggleSidebar, onOpenDocument, documentVersionCount }: HeaderProps) {
  return (
    <header className="bg-n-100 dark:bg-n-15 border-b border-n-95 dark:border-n-25 px-4 h-[52px] flex items-center gap-3">
      {/* Sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-n-95 dark:hover:bg-n-25 text-n-40 dark:text-n-70 transition-colors cursor-pointer"
        title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {sidebarOpen ? (
            <>
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </>
          ) : (
            <>
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </>
          )}
        </svg>
      </button>

      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 overflow-hidden">
        <img src={icons.appIcon} alt="Travel Planner" className="w-8 h-8 object-cover" />
      </div>
      <div>
        <h1 className="text-[15px] font-semibold text-n-10 dark:text-n-90 leading-tight">Multi-Agent Travel Planner</h1>
        <p className="text-xs text-n-60 dark:text-n-50">Powered by shared scratchpad memory</p>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-xs text-n-60 dark:text-n-50 hidden sm:block">Challenge 06 — Agents Scratchpad</span>

        {/* Document modal button */}
        <button
          onClick={onOpenDocument}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-n-40 dark:text-n-70 hover:bg-n-95 dark:hover:bg-n-25 border border-n-90 dark:border-n-25 transition-colors cursor-pointer"
          title="Shared Document"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          Document
          {documentVersionCount > 0 && (
            <span className="bg-p-50 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center leading-none">
              {documentVersionCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
