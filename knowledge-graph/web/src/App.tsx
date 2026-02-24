import { useState, useCallback, useEffect, useRef } from "react";

interface Question {
  id: number;
  question: string;
}

interface ToolCall {
  tool: string;
  summary?: string;
}

interface PanelState {
  status: "idle" | "running" | "done";
  tools: ToolCall[];
  answer: string;
}

const EMPTY_PANEL: PanelState = { status: "idle", tools: [], answer: "" };

function ToolLine({ tc }: { tc: ToolCall }) {
  return (
    <div className="flex items-start gap-2 py-1 text-sm font-mono animate-fade-in">
      <span className="text-emerald-400 shrink-0 mt-0.5">$</span>
      <div>
        <span className="text-gray-200">{tc.tool}</span>
        {tc.summary && (
          <span className="text-gray-500 ml-2">{tc.summary}</span>
        )}
      </div>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  state,
  accent,
}: {
  title: string;
  subtitle: string;
  state: PanelState;
  accent: string;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [state.tools.length, state.answer]);

  return (
    <div className={`flex-1 min-w-0 flex flex-col rounded-lg border ${accent} bg-gray-900/60`}>
      <div className={`px-4 py-2.5 border-b ${accent} bg-gray-900/80 rounded-t-lg flex items-center justify-between`}>
        <div>
          <h3 className="text-sm font-semibold text-gray-100">{title}</h3>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
        {state.status === "running" && (
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
        )}
        {state.status === "done" && (
          <span className="text-xs text-gray-500">Done</span>
        )}
      </div>
      <div className="flex-1 p-4 overflow-y-auto max-h-[60vh] space-y-3">
        {/* Tool calls */}
        {state.tools.length > 0 && (
          <div className="rounded border border-gray-700 bg-gray-950/50 px-3 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-gray-600 mb-1">
              Tool Calls
            </div>
            {state.tools.map((tc, i) => (
              <ToolLine key={i} tc={tc} />
            ))}
          </div>
        )}
        {/* Running indicator before answer */}
        {state.status === "running" && state.tools.length > 0 && !state.answer && (
          <div className="flex items-center gap-2 text-xs text-gray-500 py-1">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-gray-700 border-t-emerald-400" />
            Reasoning...
          </div>
        )}
        {/* Answer */}
        {state.answer && (
          <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap animate-fade-in">
            {state.answer}
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}

export default function App() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [rag, setRag] = useState<PanelState>(EMPTY_PANEL);
  const [graph, setGraph] = useState<PanelState>(EMPTY_PANEL);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch("/api/questions")
      .then((r) => r.json())
      .then(setQuestions)
      .catch(() => {});
  }, []);

  const runComparison = useCallback((id: number) => {
    // Abort any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSelected(id);
    setRag(EMPTY_PANEL);
    setGraph(EMPTY_PANEL);
    setRunning(true);

    const evtSource = new EventSource(`/api/compare/${id}`);

    evtSource.addEventListener("rag_start", () => {
      setRag((p) => ({ ...p, status: "running" }));
    });
    evtSource.addEventListener("rag_tool", (e) => {
      const d = JSON.parse(e.data);
      setRag((p) => ({ ...p, tools: [...p.tools, { tool: d.tool }] }));
    });
    evtSource.addEventListener("rag_answer", (e) => {
      const d = JSON.parse(e.data);
      setRag((p) => ({ ...p, status: "done", answer: d.answer }));
    });
    evtSource.addEventListener("graph_start", () => {
      setGraph((p) => ({ ...p, status: "running" }));
    });
    evtSource.addEventListener("graph_tool", (e) => {
      const d = JSON.parse(e.data);
      setGraph((p) => ({
        ...p,
        tools: [...p.tools, { tool: d.tool, summary: d.summary }],
      }));
    });
    evtSource.addEventListener("graph_answer", (e) => {
      const d = JSON.parse(e.data);
      setGraph((p) => ({ ...p, status: "done", answer: d.answer }));
    });
    evtSource.addEventListener("done", () => {
      setRunning(false);
      evtSource.close();
    });
    evtSource.onerror = () => {
      setRunning(false);
      evtSource.close();
    };

    // Cleanup on abort
    controller.signal.addEventListener("abort", () => {
      evtSource.close();
      setRunning(false);
    });
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm">
        <div className="max-w-screen-2xl mx-auto px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              Knowledge Graph Comparison
            </h1>
            <p className="text-xs text-gray-500">
              RAG-only vs Agentic Graph Search
            </p>
          </div>
          <span className="text-[10px] uppercase tracking-widest text-gray-600 border border-gray-800 rounded px-2 py-0.5">
            Biomedical
          </span>
        </div>
      </header>

      <div className="flex-1 flex flex-col max-w-screen-2xl mx-auto w-full px-6 py-4 gap-4">
        {/* Question bar */}
        <div className="flex flex-wrap gap-2">
          {questions.map((q) => (
            <button
              key={q.id}
              onClick={() => runComparison(q.id)}
              disabled={running}
              className={`px-3 py-1.5 rounded text-xs transition-all
                ${
                  selected === q.id
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
                }
                ${running ? "opacity-50 cursor-wait" : "cursor-pointer"}
              `}
              title={q.question}
            >
              <span className="font-semibold mr-1.5">Q{q.id}</span>
              <span className="hidden sm:inline">
                {q.question.length > 60
                  ? q.question.slice(0, 57) + "..."
                  : q.question}
              </span>
              <span className="sm:hidden">
                {q.question.split(".")[0].split("?")[0].slice(0, 30)}...
              </span>
            </button>
          ))}
        </div>

        {/* Selected question full text */}
        {selected && (
          <div className="text-sm text-gray-400 bg-gray-900/40 border border-gray-800 rounded px-4 py-2">
            {questions.find((q) => q.id === selected)?.question}
          </div>
        )}

        {/* Two-column comparison */}
        {selected ? (
          <div className="flex-1 flex flex-col lg:flex-row gap-4 min-h-0">
            <Panel
              title="RAG-only"
              subtitle="Hybrid search, then LLM"
              state={rag}
              accent="border-gray-700"
            />
            <Panel
              title="Agentic Graph"
              subtitle="LLM decides which tools to call"
              state={graph}
              accent="border-blue-800"
            />
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
            Select a question to run the comparison
          </div>
        )}
      </div>
    </div>
  );
}
