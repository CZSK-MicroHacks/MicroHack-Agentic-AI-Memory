export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3 shadow-sm">
      <span className="text-2xl">✈️</span>
      <div>
        <h1 className="text-lg font-bold text-gray-800">Multi-Agent Travel Planner</h1>
        <p className="text-xs text-gray-500">Powered by shared scratchpad memory</p>
      </div>
      <div className="ml-auto text-xs text-gray-400">Challenge 06 — Agents Scratchpad</div>
    </header>
  );
}
