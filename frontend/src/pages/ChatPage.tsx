import React from 'react';
import { ChatInterface } from '../components/chat/ChatInterface';

export const ChatPage: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="h-16 px-8 border-b border-slate-200 flex items-center justify-between bg-white shrink-0">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Enterprise Search & Citations</h2>
          <p className="text-xs text-slate-500">Atomic verification, prompt-injection defense, and citation grounding</p>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ChatInterface />
      </div>
    </div>
  );
};
