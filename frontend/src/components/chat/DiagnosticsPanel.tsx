import React, { useState } from 'react';
import { Activity, ChevronDown, ChevronUp, DollarSign, Clock, Cpu } from 'lucide-react';
import type { RAGDiagnosticsResponse } from '../../types/rag';

interface DiagnosticsPanelProps {
  diagnostics: RAGDiagnosticsResponse;
}

export const DiagnosticsPanel: React.FC<DiagnosticsPanelProps> = ({ diagnostics }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-3 border border-slate-200 rounded-xl overflow-hidden text-xs bg-slate-50/50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-2 flex items-center justify-between text-slate-600 hover:bg-slate-100/60 transition-colors font-medium"
      >
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-indigo-600" />
          <span>Performance & Cost Diagnostics</span>
          <span className="text-[11px] text-slate-400">({diagnostics.total_latency_ms.toFixed(0)} ms)</span>
        </div>
        {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>

      {isOpen && (
        <div className="p-4 border-t border-slate-200 bg-white grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="space-y-1">
            <div className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
              <Cpu className="w-3 h-3" /> Model
            </div>
            <div className="font-semibold text-slate-800">{diagnostics.model}</div>
          </div>

          <div className="space-y-1">
            <div className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
              <Clock className="w-3 h-3" /> Latency Breakdown
            </div>
            <div className="text-slate-800">
              R: {diagnostics.retrieval_latency_ms.toFixed(0)}ms | G: {diagnostics.generation_latency_ms.toFixed(0)}ms
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-[11px] text-slate-400 font-medium">Tokens (In / Out)</div>
            <div className="text-slate-800">
              {diagnostics.prompt_tokens} / {diagnostics.completion_tokens} ({diagnostics.total_tokens} total)
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
              <DollarSign className="w-3 h-3" /> Estimated Cost
            </div>
            <div className="font-semibold text-indigo-600">
              ${diagnostics.estimated_cost_usd.toFixed(5)}
            </div>
          </div>

          <div className="col-span-2 sm:col-span-4 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Context Chunks: <strong>{diagnostics.context_chunks_count}</strong></span>
            <span>Verified Citations: <strong>{diagnostics.valid_citations_count}</strong></span>
            <span>Fabricated Citations Pruned: <strong>{diagnostics.fabricated_citations_count}</strong></span>
          </div>
        </div>
      )}
    </div>
  );
};
