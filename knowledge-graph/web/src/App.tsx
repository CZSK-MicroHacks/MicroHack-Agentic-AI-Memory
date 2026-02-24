import { useState, useCallback, useEffect } from "react";

interface Question {
  id: number;
  question: string;
  expected: string;
}

interface CompareResult {
  question: string;
  expected: string;
  rag_answer: string;
  rag_tools: string[];
  graph_answer: string;
  graph_tools: string[];
}

function ToolTrace({ tools, color }: { tools: string[]; color: string }) {
  if (!tools.length) return null;
  return (
    <div className={`mb-3 rounded-lg border p-3 ${color}`}>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">
        Tool Calls ({tools.length})
      </div>
      {tools.map((t, i) => (
        <div key={i} className="flex items-start gap-1.5 text-sm font-mono leading-relaxed">
          <span className="shrink-0 mt-0.5">&#x2022;</span>
          <span className="break-all">{t}</span>
        </div>
      ))}
    </div>
  );
}

function AnswerPanel({
  title,
  icon,
  answer,
  tools,
  traceColor,
  borderColor,
}: {
  title: string;
  icon: string;
  answer: string;
  tools: string[];
  traceColor: string;
  borderColor: string;
}) {
  return (
    <div className={`flex-1 min-w-0 rounded-xl border-2 ${borderColor} bg-white shadow-sm`}>
      <div className={`px-4 py-3 border-b ${borderColor} bg-gray-50 rounded-t-xl`}>
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <span>{icon}</span> {title}
        </h3>
      </div>
      <div className="p-4 space-y-3">
        <ToolTrace tools={tools} color={traceColor} />
        <div className="prose prose-sm max-w-none whitespace-pre-wrap text-gray-800 leading-relaxed">
          {answer}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load questions on mount
  useEffect(() => {
    fetch("/api/questions")
      .then((r) => r.json())
      .then(setQuestions)
      .catch(() => setError("Failed to load questions. Is the API server running?"));
  }, []);

  const runComparison = useCallback(
    async (id: number) => {
      setSelected(id);
      setResult(null);
      setError(null);
      setLoading(true);
      try {
        const resp = await fetch(`/api/compare/${id}`, { method: "POST" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data: CompareResult = await resp.json();
        setResult(data);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Request failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900">
            Knowledge Graph Comparison Demo
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            RAG-only (hybrid search) vs Agentic Graph Search &mdash; Biomedical Drug Interactions
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Question selector */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {questions.map((q) => (
            <button
              key={q.id}
              onClick={() => runComparison(q.id)}
              disabled={loading}
              className={`text-left p-4 rounded-xl border-2 transition-all duration-200
                ${
                  selected === q.id
                    ? "border-blue-500 bg-blue-50 shadow-md"
                    : "border-gray-200 bg-white hover:border-blue-300 hover:shadow"
                }
                ${loading ? "opacity-60 cursor-wait" : "cursor-pointer"}
              `}
            >
              <div className="text-xs font-semibold text-blue-600 mb-1">Q{q.id}</div>
              <div className="text-sm font-medium text-gray-800">{q.question}</div>
              <div className="text-xs text-gray-400 mt-2">
                Expected: {q.expected}
              </div>
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <div className="flex flex-col items-center gap-3">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
              <span className="text-sm text-gray-500">
                Running comparison&hellip; Agent is reasoning and calling tools.
              </span>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-4">
            <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
              <span className="font-semibold text-amber-800">Question:</span>{" "}
              <span className="text-amber-900">{result.question}</span>
              <div className="text-xs text-amber-600 mt-1">
                Expected: {result.expected}
              </div>
            </div>

            <div className="flex flex-col lg:flex-row gap-4">
              <AnswerPanel
                title="RAG-only"
                icon="&#x1F4C4;"
                answer={result.rag_answer}
                tools={result.rag_tools}
                traceColor="bg-gray-50 border-gray-200"
                borderColor="border-gray-300"
              />
              <AnswerPanel
                title="Agentic Graph"
                icon="&#x1F517;"
                answer={result.graph_answer}
                tools={result.graph_tools}
                traceColor="bg-blue-50 border-blue-200"
                borderColor="border-blue-400"
              />
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !result && !error && questions.length > 0 && (
          <div className="text-center py-16 text-gray-400">
            <div className="text-4xl mb-3">&#x1F50D;</div>
            <p>Select a question above to run the comparison.</p>
          </div>
        )}
      </main>
    </div>
  );
}
