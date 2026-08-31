import React from 'react';
import { X, FileText, Bookmark } from 'lucide-react';
import type { CitationItem } from '../../types/rag';

interface CitationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citation: CitationItem | null;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({
  isOpen,
  onClose,
  citation,
}) => {
  if (!isOpen || !citation) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/30 backdrop-blur-xs flex justify-end">
      <div className="w-full max-w-md bg-white h-full shadow-2xl border-l border-slate-200 flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="h-16 px-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 font-mono text-xs font-bold rounded">
              {citation.citation_id}
            </span>
            <span className="text-xs font-medium text-slate-500">Verified Evidence</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 flex-1 overflow-y-auto">
          {/* Metadata Card */}
          <div className="p-4 bg-slate-50 border border-slate-100 rounded-xl space-y-2 text-xs">
            <div className="flex items-center gap-2 text-slate-800 font-medium truncate">
              <FileText className="w-4 h-4 text-indigo-600 shrink-0" />
              <span className="truncate">{citation.filename}</span>
            </div>
            <div className="flex items-center gap-4 text-slate-500 text-[11px] pt-1 border-t border-slate-200/60">
              {citation.page_number && (
                <span>Page: <strong>{citation.page_number}</strong></span>
              )}
              {citation.char_start !== null && citation.char_end !== null && (
                <span>Char Span: {citation.char_start}–{citation.char_end}</span>
              )}
            </div>
          </div>

          {/* Quoted Passage */}
          <div>
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Bookmark className="w-3.5 h-3.5 text-indigo-600" />
              Grounding Text Passage
            </h4>
            <div className="p-4 bg-amber-50/40 border border-amber-200/60 rounded-xl text-xs leading-relaxed text-slate-800 font-serif whitespace-pre-wrap">
              "{citation.snippet}"
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50 text-[11px] text-slate-500">
          Source verified against tenant-authorized vector chunk database.
        </div>
      </div>
    </div>
  );
};
