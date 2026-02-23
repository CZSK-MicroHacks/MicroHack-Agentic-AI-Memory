import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { icons } from './icons';

interface ChatPanelProps {
  onSend: (message: string) => void;
  status: 'idle' | 'running' | 'finished' | 'error';
  finalAnswer: string;
  facilitatorStream: string;
}

export default function ChatPanel({ onSend, status, finalAnswer, facilitatorStream }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [finalAnswer, facilitatorStream]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || status === 'running') return;
    onSend(msg);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto panel-scroll">
        <div className="max-w-3xl mx-auto px-6 py-4 space-y-4">
        {status === 'idle' && (
          <div className="text-center text-n-60 dark:text-n-50 mt-8 animate-fade-in">
            <p className="text-4xl mb-3"><img src={icons.globeIcon} alt="Globe" className="w-16 h-16 mx-auto" /></p>
            <p className="text-sm mb-4 text-n-50 dark:text-n-60">Ask me to plan your next trip!</p>
            <div className="space-y-2 max-w-md mx-auto text-left">
              {[
                'Naplánuj výlet do Prahy na 2 dny. Chci ochutnat něco typicky českého, zajít na koncert a něco vidět.',
                'Naplánuj návštěvu Tbilisi v Gruzii na 3 dny. Rád bych se šel podívat na oranžové víno, ochutnat, prohlédnout město.',
                'Chci se podívat do Dubaje, nějaké zajímavé zážitky, výstavy, místa. Budu tam 3 dny.',
              ].map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => { onSend(prompt); }}
                  className="w-full text-left px-3 py-2.5 text-[13px] text-n-30 dark:text-n-80 bg-n-100 dark:bg-n-20 rounded-xl border border-n-90 dark:border-n-25 hover:bg-n-98 dark:hover:bg-n-25 hover:border-n-80 dark:hover:border-n-35 transition-colors cursor-pointer"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {status === 'running' && !finalAnswer && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center gap-2 text-sm text-p-50 dark:text-p-60">
              <span className="animate-pulse-dot">●</span>
              <span>Agents are working on your travel plan...</span>
            </div>
            {facilitatorStream && (
              <div className="bg-n-98 dark:bg-n-20 rounded-xl p-3 border border-n-90 dark:border-n-25">
                <div className="text-xs font-medium text-n-50 dark:text-n-60 mb-1 flex items-center gap-1">
                  <img src={icons.agentFacilitator} alt="" className="w-5 h-5" /> Facilitator
                </div>
                <div className="text-sm text-n-10 dark:text-n-90 markdown-content">
                  <ReactMarkdown>{facilitatorStream}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}

        {finalAnswer && (
          <div className="bg-n-100 dark:bg-n-20 rounded-xl p-4 border border-n-90 dark:border-n-25 animate-fade-in">
            <div className="text-xs font-medium text-green-600 dark:text-green-400 mb-2 flex items-center gap-1">
              <img src={icons.checkmarkIcon} alt="" className="w-5 h-5" /> Final Travel Plan
            </div>
            <div className="text-sm text-n-10 dark:text-n-90 markdown-content">
              <ReactMarkdown>{finalAnswer}</ReactMarkdown>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="bg-red-50 dark:bg-red-950 rounded-xl p-3 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 flex items-center gap-1.5">
            <img src={icons.warningIcon} alt="" className="w-5 h-5" /> An error occurred. Check the timeline for details.
          </div>
        )}

        <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-n-95 dark:border-n-25 bg-n-100 dark:bg-n-15">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto px-6 py-3">
        <div className="flex gap-0 border border-n-90 dark:border-n-25 rounded-2xl bg-n-100 dark:bg-n-20 overflow-hidden focus-within:border-n-70 dark:focus-within:border-n-40 focus-within:shadow-[0_0_0_1px] focus-within:shadow-n-70 dark:focus-within:shadow-n-40 transition-all">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Where would you like to travel?"
            disabled={status === 'running'}
            className="flex-1 px-4 py-3.5 text-sm bg-transparent border-none outline-none text-n-10 dark:text-n-90 placeholder-n-60 dark:placeholder-n-50 disabled:opacity-50 disabled:bg-transparent font-sans"
          />
          <button
            type="submit"
            disabled={status === 'running' || !input.trim()}
            className="flex items-center justify-center w-10 h-10 m-1 rounded-[10px] border-none bg-n-10 dark:bg-n-90 text-n-100 dark:text-n-10 cursor-pointer transition-opacity disabled:opacity-30 disabled:cursor-default hover:not-disabled:opacity-85"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
          </button>
        </div>
        </form>
      </div>
    </div>
  );
}
