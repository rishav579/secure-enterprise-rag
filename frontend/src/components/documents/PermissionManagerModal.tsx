import React, { useEffect, useState } from 'react';
import { UserPlus, Trash2, ShieldCheck, AlertCircle } from 'lucide-react';
import { documentsApi } from '../../api/documents';
import type { DocumentPermissionResponse, DocumentResponse } from '../../types/document';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import { Badge } from '../common/Badge';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { APIError } from '../../api/client';

interface PermissionManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: DocumentResponse | null;
}

export const PermissionManagerModal: React.FC<PermissionManagerModalProps> = ({
  isOpen,
  onClose,
  document,
}) => {
  const [permissions, setPermissions] = useState<DocumentPermissionResponse[]>([]);
  const [userIdInput, setUserIdInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isGranting, setIsGranting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPermissions = async () => {
    if (!document) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await documentsApi.listPermissions(document.id);
      setPermissions(res.items);
    } catch (err: any) {
      if (err instanceof APIError) {
        setError(err.message);
      } else {
        setError('Failed to fetch permissions.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && document) {
      fetchPermissions();
    } else {
      setPermissions([]);
      setUserIdInput('');
      setError(null);
    }
  }, [isOpen, document]);

  const handleGrant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!document || !userIdInput.trim()) return;

    setError(null);
    setIsGranting(true);

    try {
      await documentsApi.grantPermission(document.id, userIdInput.trim(), 'read');
      setUserIdInput('');
      await fetchPermissions();
    } catch (err: any) {
      if (err instanceof APIError) {
        setError(err.message);
      } else {
        setError('Failed to grant permission.');
      }
    } finally {
      setIsGranting(false);
    }
  };

  const handleRevoke = async (userId: string) => {
    if (!document) return;
    setError(null);
    try {
      await documentsApi.revokePermission(document.id, userId);
      await fetchPermissions();
    } catch (err: any) {
      if (err instanceof APIError) {
        setError(err.message);
      } else {
        setError('Failed to revoke permission.');
      }
    }
  };

  if (!document) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Manage Permissions: ${document.filename}`}
      maxWidth="lg"
    >
      <div className="space-y-6">
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-xs text-red-700 font-medium">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Grant New Permission */}
        <form onSubmit={handleGrant} className="p-4 bg-slate-50 border border-slate-100 rounded-xl space-y-3">
          <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
            <UserPlus className="w-3.5 h-3.5" />
            Grant Read Access
          </h4>
          <div className="flex gap-2">
            <Input
              placeholder="User UUID (must belong to this tenant)"
              value={userIdInput}
              onChange={(e) => setUserIdInput(e.target.value)}
              required
              className="text-xs"
            />
            <Button type="submit" size="sm" isLoading={isGranting} disabled={!userIdInput.trim()}>
              Grant
            </Button>
          </div>
          <p className="text-[11px] text-slate-500">
            Target user must belong to the current tenant. Cross-tenant sharing is strictly prohibited by backend policy.
          </p>
        </form>

        {/* Existing Grants List */}
        <div>
          <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5" />
            Active Explicit Grants
          </h4>

          {isLoading ? (
            <div className="py-6 flex justify-center">
              <LoadingSpinner size="md" />
            </div>
          ) : permissions.length === 0 ? (
            <div className="p-4 border border-dashed border-slate-200 rounded-lg text-center text-xs text-slate-500">
              No explicit user grants. Default access policy governs visibility ({document.min_role} or owner).
            </div>
          ) : (
            <div className="divide-y divide-slate-100 border border-slate-100 rounded-lg overflow-hidden">
              {permissions.map((p) => (
                <div key={p.id} className="p-3 flex items-center justify-between bg-white hover:bg-slate-50/50 text-xs">
                  <div>
                    <div className="font-mono text-slate-800 text-[11px]">{p.user_id}</div>
                    <div className="text-slate-400 text-[10px]">Granted: {new Date(p.created_at).toLocaleString()}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="primary" size="sm">{p.permission.toUpperCase()}</Badge>
                    <button
                      onClick={() => handleRevoke(p.user_id)}
                      className="p-1 text-slate-400 hover:text-red-600 rounded hover:bg-red-50 transition-colors"
                      title="Revoke Permission"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};
