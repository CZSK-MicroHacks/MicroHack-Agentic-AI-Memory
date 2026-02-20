import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

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
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">💬 Chat</h2>
      </div>

      <div className="flex-1 overflow-y-auto panel-scroll p-4 space-y-4">
        {status === 'idle' && (
          <div className="text-center text-gray-400 mt-8">
            <p className="text-4xl mb-3">🌍</p>
            <p className="text-sm mb-4">Ask me to plan your next trip!</p>
            <div className="space-y-2 max-w-md mx-auto text-left">
              {[
                'Naplánuj výlet do Prahy na 2 dny. Chci ochutnat něco typicky českého, zajít na koncert a něco vidět.',
                'Naplánuj návštěvu Tbilisi v Gruzii na 3 dny. Rád bych se šel podívat na oranžové víno, ochutnat, prohlédnout město.',
                'Chci se podívat do Dubaje, nějaké zajímavé zážitky, výstavy, místa. Budu tam 3 dny.',
              ].map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => { onSend(prompt); }}
                  className="w-full text-left px-3 py-2 text-xs text-gray-600 bg-gray-50 rounded-lg border border-gray-200 hover:bg-purple-50 hover:border-purple-300 hover:text-purple-700 transition-colors cursor-pointer"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {status === 'running' && !finalAnswer && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-purple-600">
              <span className="animate-pulse-dot">●</span>
              <span>Agents are working on your travel plan...</span>
            </div>
            {facilitatorStream && (
              <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
                <div className="text-xs font-medium text-purple-600 mb-1">🎯 Facilitator</div>
                <div className="text-sm text-gray-700 markdown-content">
                  <ReactMarkdown>{facilitatorStream}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}

        {finalAnswer && (
          <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
            <div className="text-xs font-medium text-green-600 mb-2 flex items-center gap-1">
              ✅ Final Travel Plan
            </div>
            <div className="text-sm text-gray-700 markdown-content">
              <ReactMarkdown>{finalAnswer}</ReactMarkdown>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="bg-red-50 rounded-lg p-3 border border-red-200 text-sm text-red-700">
            ⚠️ An error occurred. Check the timeline for details.
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="p-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Where would you like to travel?"
            disabled={status === 'running'}
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
          />
          <button
            type="submit"
            disabled={status === 'running' || !input.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {status === 'running' ? '⏳' : '✈️ Plan'}
          </button>
        </div>
      </form>
    </div>
  );
}
