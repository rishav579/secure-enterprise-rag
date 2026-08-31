import React, { useEffect, useState } from 'react';
import { Upload, RefreshCw } from 'lucide-react';
import type { DocumentResponse } from '../types/document';
import { documentsApi } from '../api/documents';
import { DocumentList } from '../components/documents/DocumentList';
import { DocumentUploadModal } from '../components/documents/DocumentUploadModal';
import { Button } from '../components/common/Button';

export const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const res = await documentsApi.list();
      setDocuments(res.items);
    } catch {
      setDocuments([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="h-16 px-8 border-b border-slate-200 flex items-center justify-between bg-white shrink-0">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Enterprise Documents</h2>
          <p className="text-xs text-slate-500">Tenant-isolated storage, PII scrubbing, and chunk embeddings</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={fetchDocuments} isLoading={isLoading}>
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setIsUploadOpen(true)}>
            <Upload className="w-3.5 h-3.5 mr-1.5" />
            Upload PDF
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <DocumentList
          documents={documents}
          onRefresh={fetchDocuments}
          isLoading={isLoading}
        />
      </div>

      <DocumentUploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadSuccess={fetchDocuments}
      />
    </div>
  );
};
