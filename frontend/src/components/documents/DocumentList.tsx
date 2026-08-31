import React, { useState } from 'react';
import { FileText, Trash2, Key, AlertCircle } from 'lucide-react';
import type { DocumentResponse } from '../../types/document';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { useAuth } from '../../context/AuthContext';
import { documentsApi } from '../../api/documents';
import { PermissionManagerModal } from './PermissionManagerModal';

interface DocumentListProps {
  documents: DocumentResponse[];
  onRefresh: () => void;
  isLoading: boolean;
}

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  onRefresh,
  isLoading,
}) => {
  const { user } = useAuth();
  const [selectedDocForPermissions, setSelectedDocForPermissions] = useState<DocumentResponse | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async (docId: string) => {
    if (!window.confirm('Are you sure you want to permanently delete this document and all associated chunks?')) {
      return;
    }

    setDeletingId(docId);
    setError(null);

    try {
      await documentsApi.delete(docId);
      onRefresh();
    } catch (err: any) {
      setError(err.message || 'Failed to delete document.');
    } finally {
      setDeletingId(null);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-xs text-red-700 font-medium">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 text-slate-500 font-semibold">
            <tr>
              <th scope="col" className="px-6 py-3">Document Name</th>
              <th scope="col" className="px-6 py-3">Size</th>
              <th scope="col" className="px-6 py-3">Access Tier</th>
              <th scope="col" className="px-6 py-3">Status</th>
              <th scope="col" className="px-6 py-3">Ingested Date</th>
              <th scope="col" className="px-6 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {documents.length === 0 && !isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-slate-400">
                  <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                  No documents found in this tenant scope.
                </td>
              </tr>
            )}

            {documents.map((doc) => {
              // Role-aware presentation: manage button visible if user is owner or admin
              const canManage = user?.role === 'admin' || user?.id === doc.owner_id;

              return (
                <tr key={doc.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-6 py-4 font-medium text-slate-900 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-indigo-600 shrink-0" />
                    <span className="truncate max-w-xs">{doc.filename}</span>
                  </td>
                  <td className="px-6 py-4 text-slate-500">{formatBytes(doc.file_size_bytes)}</td>
                  <td className="px-6 py-4">
                    <Badge variant={doc.min_role === 'admin' ? 'warning' : 'primary'} size="sm">
                      {doc.min_role === 'admin' ? 'Admin Only' : 'Employee'}
                    </Badge>
                  </td>
                  <td className="px-6 py-4">
                    <Badge
                      variant={
                        doc.status === 'completed'
                          ? 'success'
                          : doc.status === 'failed'
                          ? 'danger'
                          : 'neutral'
                      }
                      size="sm"
                    >
                      {doc.status.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 text-slate-500">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right space-x-2">
                    {canManage && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setSelectedDocForPermissions(doc)}
                        title="Manage Permissions"
                      >
                        <Key className="w-3.5 h-3.5 mr-1" />
                        Permissions
                      </Button>
                    )}
                    {canManage && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(doc.id)}
                        isLoading={deletingId === doc.id}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        title="Delete Document"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <PermissionManagerModal
        isOpen={!!selectedDocForPermissions}
        onClose={() => setSelectedDocForPermissions(null)}
        document={selectedDocForPermissions}
      />
    </div>
  );
};
