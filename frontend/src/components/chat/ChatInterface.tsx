import React, { useState } from 'react';
import { Send, Shield, Info, AlertTriangle, BookOpen } from 'lucide-react';
import { ragApi } from '../../api/rag';
import type { CitationItem, RAGQueryResponse } from '../../types/rag';
import { Button } from '../common/Button';
import { CitationDrawer } from './CitationDrawer';
import { DiagnosticsPanel } from './DiagnosticsPanel';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { APIError } from '../../api/client';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  response?: RAGQueryResponse;
}

export const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [includeDiagnostics, setIncludeDiagnostics] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Selected citation for side drawer preview
  const [activeCitation, setActiveCitation] = useState<CitationItem | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      sender: 'user',
      content: query.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const currentQuery = query.trim();
    setQuery('');
    setError(null);
    setIsLoading(true);

    try {
      // Atomic verification: Request returns only after full citation & grounding check
      const res = await ragApi.query(currentQuery, topK, includeDiagnostics);
      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        sender: 'assistant',
        content: res.answer,
        response: res,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      if (err instanceof APIError) {
        setError(err.message);
      } else {
        setError('Failed to reach retrieval service.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Helper to render answer text with clickable citation badges
  const renderGroundedContent = (text: string, citations: CitationItem[]) => {
    const citationRegex = /(\[DOC-\d+\])/g;
    const parts = text.split(citationRegex);

    return (
      <span>
        {parts.map((part, i) => {
          if (citationRegex.test(part)) {
            const found = citations.find((c) => c.citation_id.toUpperCase() === part.toUpperCase());
            return (
              <button
                key={i}
                onClick={() => found && setActiveCitation(found)}
                className={`inline-flex items-center px-1.5 py-0.5 mx-0.5 font-mono text-[11px] font-bold rounded border transition-all ${
                  found
                    ? 'bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100 hover:border-indigo-300 cursor-pointer'
                    : 'bg-slate-100 border-slate-200 text-slate-500 cursor-not-allowed'
                }`}
                title={found ? `View source: ${found.filename}` : 'Source unverified'}
              >
                {part}
              </button>
            );
          }
          return <span key={i}>{part}</span>;
        })}
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto my-auto py-16">
            <div className="w-12 h-12 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-slate-800 mb-1">Grounded Enterprise Knowledge</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Ask questions about tenant documents. Every answer is retrieved using hybrid search,
              guarded against prompt injection, and backed by verifiable citations.
            </p>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.sender === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-2xl rounded-2xl px-5 py-3.5 text-sm leading-relaxed ${
                m.sender === 'user'
                  ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-200'
                  : 'bg-white text-slate-900 border border-slate-200 shadow-sm'
              }`}
            >
              {m.sender === 'assistant' && m.response ? (
                <div>
                  {/* Refusal / Insufficient Evidence Banner */}
                  {m.response.is_refusal && (
                    <div className="mb-3 p-3 bg-amber-50/70 border border-amber-200 rounded-xl flex items-start gap-2 text-xs text-amber-800 font-medium">
                      <Info className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
                      <span>{m.response.answer}</span>
                    </div>
                  )}

                  {/* Grounded content with clickable badges */}
                  {!m.response.is_refusal && (
                    <div>{renderGroundedContent(m.content, m.response.citations)}</div>
                  )}

                  {/* Citations Summary Footer */}
                  {m.response.citations.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold text-slate-500 flex items-center gap-1">
                        <BookOpen className="w-3.5 h-3.5" /> Cited Sources:
                      </span>
                      {m.response.citations.map((c) => (
                        <button
                          key={c.citation_id}
                          onClick={() => setActiveCitation(c)}
                          className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium rounded-md transition-colors flex items-center gap-1"
                        >
                          <span className="font-mono text-indigo-600">{c.citation_id}</span>
                          <span className="truncate max-w-[140px]">{c.filename}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Optional Safe Diagnostics */}
                  {m.response.diagnostics && (
                    <DiagnosticsPanel diagnostics={m.response.diagnostics} />
                  )}
                </div>
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-start">
            <div className="bg-white border border-slate-200 rounded-2xl px-5 py-3.5 shadow-sm flex items-center gap-3 text-xs text-slate-500 font-medium">
              <LoadingSpinner size="sm" />
              <span>Retrieving documents and verifying citations...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium flex items-center gap-2 max-w-xl mx-auto">
            <AlertTriangle className="w-4 h-4 shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Input Bar & Config Controls */}
      <div className="p-4 bg-white border-t border-slate-200">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Ask a question about authorized enterprise policies..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 rounded-xl border border-slate-300 px-4 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              disabled={isLoading}
            />
            <Button type="submit" isLoading={isLoading} disabled={!query.trim()} className="px-5">
              <Send className="w-4 h-4 mr-1.5" /> Ask
            </Button>
          </div>

          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <span>Top Context Chunks:</span>
                <select
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="rounded border border-slate-200 text-xs px-1.5 py-0.5 bg-slate-50 focus:outline-none"
                  disabled={isLoading}
                >
                  <option value={3}>3</option>
                  <option value={5}>5 (default)</option>
                  <option value={10}>10 (max)</option>
                </select>
              </label>

              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={includeDiagnostics}
                  onChange={(e) => setIncludeDiagnostics(e.target.checked)}
                  className="rounded text-indigo-600 focus:ring-indigo-500"
                  disabled={isLoading}
                />
                <span>Include Performance & Cost Diagnostics</span>
              </label>
            </div>

            <div className="text-[11px] text-slate-400">
              Citations strictly mapped to authorized PostgreSQL vector embeddings.
            </div>
          </div>
        </form>
      </div>

      <CitationDrawer
        isOpen={!!activeCitation}
        onClose={() => setActiveCitation(null)}
        citation={activeCitation}
      />
    </div>
  );
};
