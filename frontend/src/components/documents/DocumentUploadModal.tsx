import React, { useState } from 'react';
import { Upload, AlertCircle } from 'lucide-react';
import { documentsApi } from '../../api/documents';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import type { UserRole } from '../../types/auth';
import { APIError } from '../../api/client';

interface DocumentUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadSuccess: () => void;
}

export const DocumentUploadModal: React.FC<DocumentUploadModalProps> = ({
  isOpen,
  onClose,
  onUploadSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [minRole, setMinRole] = useState<UserRole>('employee');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Client-side UX validation limits (Strict backend validation remains authoritative)
  const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];

      // UX validation only: check extension and size
      if (!selected.name.toLowerCase().endsWith('.pdf') && selected.type !== 'application/pdf') {
        setError('Only PDF documents (.pdf) are accepted.');
        setFile(null);
        return;
      }

      if (selected.size > MAX_FILE_SIZE_BYTES) {
        setError('File size exceeds the 10 MB limit.');
        setFile(null);
        return;
      }

      setFile(selected);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a PDF file to upload.');
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      await documentsApi.upload(file, minRole);
      setFile(null);
      onUploadSuccess();
      onClose();
    } catch (err: any) {
      if (err instanceof APIError) {
        setError(err.message);
      } else {
        setError('Failed to upload document.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Upload PDF Document">
      <form onSubmit={handleUpload} className="space-y-4">
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-xs text-red-700 font-medium">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            PDF Document
          </label>
          <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-slate-200 border-dashed rounded-xl hover:border-indigo-400 transition-colors bg-slate-50/50">
            <div className="space-y-1 text-center">
              <Upload className="mx-auto h-8 w-8 text-slate-400" />
              <div className="flex text-sm text-slate-600 justify-center">
                <label className="relative cursor-pointer rounded-md font-medium text-indigo-600 hover:text-indigo-500 focus-within:outline-none">
                  <span>Upload a file</span>
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    className="sr-only"
                    onChange={handleFileChange}
                    disabled={isLoading}
                  />
                </label>
                <p className="pl-1">or drag and drop</p>
              </div>
              <p className="text-xs text-slate-500">PDF up to 10 MB</p>
              {file && (
                <p className="text-xs font-semibold text-indigo-700 pt-2">
                  Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                </p>
              )}
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Minimum Access Role
          </label>
          <select
            value={minRole}
            onChange={(e) => setMinRole(e.target.value as UserRole)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            disabled={isLoading}
          >
            <option value="employee">Employee (All tenant employees)</option>
            <option value="admin">Admin Only (Confidential / Administrators)</option>
          </select>
          <p className="mt-1 text-xs text-slate-500">
            Admin-only documents are only accessible to tenant administrators unless explicitly granted.
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
          <Button variant="secondary" onClick={onClose} disabled={isLoading} type="button">
            Cancel
          </Button>
          <Button type="submit" isLoading={isLoading} disabled={!file}>
            Process & Ingest
          </Button>
        </div>
      </form>
    </Modal>
  );
};
