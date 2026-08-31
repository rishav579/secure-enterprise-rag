import React from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, FileText, Shield, LogOut } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Badge } from '../common/Badge';

export const Sidebar: React.FC = () => {
  const { user, logout } = useAuth();

  const navItems = [
    { to: '/chat', label: 'Search & Q&A', icon: MessageSquare },
    { to: '/documents', label: 'Documents', icon: FileText },
  ];

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col h-screen select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-6 border-b border-slate-100 gap-3">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm shadow-indigo-200">
          <Shield className="w-4 h-4" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-slate-900 tracking-tight">Enterprise RAG</h1>
          <p className="text-[11px] text-slate-500 font-medium">Secure Knowledge Base</p>
        </div>
      </div>

      {/* Tenant / Role Context Card */}
      {user && (
        <div className="p-4 mx-3 my-3 bg-slate-50 border border-slate-100 rounded-xl">
          <div className="text-xs text-slate-500 font-medium truncate mb-1">Tenant Scope</div>
          <div className="text-xs font-semibold text-slate-800 truncate mb-2">{user.tenant_id}</div>
          <div className="flex items-center gap-2">
            <Badge variant={user.role === 'admin' ? 'warning' : 'primary'} size="sm">
              {user.role.toUpperCase()}
            </Badge>
          </div>
        </div>
      )}

      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1 mt-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* User Info & Logout Footer */}
      <div className="p-3 border-t border-slate-100">
        {user && (
          <div className="px-3 py-2 mb-2">
            <div className="text-xs font-medium text-slate-900 truncate">{user.email}</div>
          </div>
        )}
        <button
          onClick={logout}
          className="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-red-50 hover:text-red-700 rounded-lg transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
      </div>
    </aside>
  );
};
