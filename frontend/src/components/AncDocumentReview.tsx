import React, { useEffect, useState, useCallback } from 'react';
import {
  Upload,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Edit3,
  FileText,
  Layers,
  Sparkles,
  Download,
  GitCompare,
  ShieldAlert,
  Eye,
  Check,
  Ban,
  HelpCircle,
} from 'lucide-react';
import { apiRequest, getStoredToken } from '../api';
import type {
  Mother,
  DocumentItem,
  ExtractedFieldItem,
  RoleType,
} from '../types';

interface Props {
  mothers: Mother[];
  documents: DocumentItem[];
  userRole: 'admin' | 'doctor' | 'nurse' | 'field_coordinator';
  onRefreshClinicData: () => Promise<void>;
  notify: (text: string, type?: 'success' | 'error') => void;
}

export default function AncDocumentReview({
  mothers,
  documents,
  userRole,
  onRefreshClinicData,
  notify,
}: Props) {
  const [selectedMotherId, setSelectedMotherId] = useState<string>(
    mothers[0]?.id || ''
  );
  const [selectedDocId, setSelectedDocId] = useState<string>('');
  const [activeDoc, setActiveDoc] = useState<DocumentItem | null>(null);
  const [selectedFieldKey, setSelectedFieldKey] = useState<string>('patient_name');
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);

  // Inline correction state per field ID
  const [fieldEdits, setFieldEdits] = useState<Record<string, string>>({});
  const [fieldNotes, setFieldNotes] = useState<Record<string, string>>({});
  const [editedRawText, setEditedRawText] = useState<string>('');

  // Live OCR Benchmark state
  const [benchmarkData, setBenchmarkData] = useState<any | null>(null);
  const [runningBenchmark, setRunningBenchmark] = useState<boolean>(false);

  const canVerify = userRole === 'admin' || userRole === 'doctor' || userRole === 'nurse';

  useEffect(() => {
    if (!selectedMotherId && mothers.length > 0) {
      setSelectedMotherId(mothers[0].id);
    }
  }, [mothers, selectedMotherId]);

  const motherDocs = documents
    .filter((d) => !selectedMotherId || d.mother_id === selectedMotherId)
    .sort((a, b) => (b.version_number || 1) - (a.version_number || 1));

  useEffect(() => {
    if (motherDocs.length > 0) {
      if (!selectedDocId || !motherDocs.some((d) => d.id === selectedDocId)) {
        setSelectedDocId(motherDocs[0].id);
      }
    } else {
      setSelectedDocId('');
      setActiveDoc(null);
    }
  }, [motherDocs, selectedDocId]);

  const loadDocumentDetail = useCallback(async (did: string) => {
    if (!did) {
      setActiveDoc(null);
      return;
    }
    try {
      const detail = await apiRequest<DocumentItem>(`/api/documents/${did}`);
      setActiveDoc(detail);
      setEditedRawText(detail.extracted_text || '');
      const initialEdits: Record<string, string> = {};
      const initialNotes: Record<string, string> = {};
      (detail.fields || []).forEach((f) => {
        initialEdits[f.id] =
          f.final_value ?? f.normalized_value ?? f.extracted_value ?? '';
        initialNotes[f.id] = f.reviewer_note ?? '';
      });
      setFieldEdits(initialEdits);
      setFieldNotes(initialNotes);
    } catch (err: any) {
      notify(err.message || 'Failed to load document details', 'error');
    }
  }, [notify]);

  useEffect(() => {
    if (selectedDocId) {
      loadDocumentDetail(selectedDocId);
    }
  }, [selectedDocId, loadDocumentDetail]);

  // Fetch authenticated preview image as Object URL
  useEffect(() => {
    let revoked = false;
    let currentUrl: string | null = null;
    async function loadPreview() {
      if (!selectedDocId) {
        setPreviewBlobUrl(null);
        return;
      }
      try {
        const headers: Record<string, string> = {};
        const tok = getStoredToken();
        if (tok) headers['Authorization'] = `Bearer ${tok}`;
        const res = await fetch(`/api/documents/${selectedDocId}/preview`, {
          headers,
          credentials: 'include',
        });
        if (!res.ok) {
          setPreviewBlobUrl(null);
          return;
        }
        const blob = await res.blob();
        if (!revoked) {
          currentUrl = URL.createObjectURL(blob);
          setPreviewBlobUrl(currentUrl);
        }
      } catch {
        if (!revoked) setPreviewBlobUrl(null);
      }
    }
    loadPreview();
    return () => {
      revoked = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [selectedDocId]);

  const handleFileUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedMotherId) return;
    const form = e.currentTarget;
    const fd = new FormData(form);
    setUploading(true);
    try {
      const created = await apiRequest<DocumentItem>(
        `/api/mothers/${selectedMotherId}/documents`,
        'POST',
        fd
      );
      form.reset();
      notify(
        `Uploaded v${created.version_number} (${created.filename}) — OCR ${created.ocr_status}`
      );
      await onRefreshClinicData();
      setSelectedDocId(created.id);
      await loadDocumentDetail(created.id);
    } catch (err: any) {
      notify(err.message || 'Upload failed', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleLoadSyntheticFixture = async (
    fixtureId: 'printed_clear' | 'partially_handwritten' | 'difficult_incomplete',
    format: 'png' | 'pdf' = 'png'
  ) => {
    if (!selectedMotherId) {
      notify('Select or register a mother first', 'error');
      return;
    }
    setUploading(true);
    try {
      const created = await apiRequest<DocumentItem>(
        `/api/mothers/${selectedMotherId}/documents/fixture/${fixtureId}?format=${format}`,
        'POST'
      );
      notify(
        `Processed synthetic fixture "${fixtureId}" (${format.toUpperCase()}) as Document v${created.version_number}`
      );
      await onRefreshClinicData();
      setSelectedDocId(created.id);
      await loadDocumentDetail(created.id);
    } catch (err: any) {
      notify(err.message || 'Fixture upload failed', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleFieldDecision = async (
    field: ExtractedFieldItem,
    decision: 'accepted' | 'corrected' | 'rejected' | 'illegible_manual'
  ) => {
    if (!activeDoc) return;
    try {
      const finalValue =
        decision === 'corrected' || decision === 'illegible_manual'
          ? fieldEdits[field.id] || ''
          : undefined;
      const updated = await apiRequest<DocumentItem>(
        `/api/documents/${activeDoc.id}/fields/${field.id}`,
        'PATCH',
        {
          decision,
          final_value: finalValue,
          reviewer_note: fieldNotes[field.id] || '',
        }
      );
      setActiveDoc(updated);
      notify(`Field "${field.field_label}" marked as ${decision.replace('_', ' ')}`);
    } catch (err: any) {
      notify(err.message || 'Field verification failed', 'error');
    }
  };

  const handleConfirmDocument = async () => {
    if (!activeDoc) return;
    try {
      const updated = await apiRequest<DocumentItem>(
        `/api/documents/${activeDoc.id}/confirm`,
        'PATCH',
        {
          corrected_text: editedRawText,
        }
      );
      setActiveDoc(updated);
      await onRefreshClinicData();
      notify(
        `Document v${updated.version_number} human-confirmed. Any differing fields queued as administrative change proposals.`
      );
    } catch (err: any) {
      notify(err.message || 'Document confirmation failed', 'error');
    }
  };

  const handleProposalDecision = async (
    proposalId: string,
    decision: 'approved' | 'rejected'
  ) => {
    try {
      await apiRequest(`/api/change-proposals/${proposalId}/decide`, 'POST', {
        decision,
        review_note: `Reviewed via ANC verification console (${decision})`,
      });
      notify(`Administrative change proposal ${decision}`);
      await onRefreshClinicData();
      if (activeDoc) {
        await loadDocumentDetail(activeDoc.id);
      }
    } catch (err: any) {
      notify(err.message || 'Failed to process change proposal', 'error');
    }
  };

  const handleRunBenchmark = async () => {
    setRunningBenchmark(true);
    try {
      const res = await apiRequest<any>('/api/documents/fixtures/evaluate');
      setBenchmarkData(res);
      notify(
        `OCR Benchmark completed: ${res.overall_present_field_accuracy_percent}% field accuracy across 3 synthetic fixtures`
      );
    } catch (err: any) {
      notify(err.message || 'Failed to run benchmark', 'error');
    } finally {
      setRunningBenchmark(false);
    }
  };

  const fields = activeDoc?.fields || [];
  const selectedField =
    fields.find((f) => f.field_key === selectedFieldKey) || fields[0] || null;
  const imgW = activeDoc?.image_width || 1050;
  const imgH = activeDoc?.image_height || 760;

  return (
    <div className="space-y-6" data-testid="anc-document-review">
      {/* Top Bar: Mother Selection + File Upload + Synthetic Fixture Evaluators */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-5 h-5 text-teal-700" />
              Evidence-Linked ANC Card Digitisation & Human Verification
            </h2>
            <p className="text-xs text-slate-600 mt-0.5">
              Select an extracted field on the right to highlight its OCR bounding-box provenance on
              the left scan. Raw OCR is never automatically written to patient records or care plans.
            </p>
          </div>
          {canVerify && (
            <button
              type="button"
              onClick={handleRunBenchmark}
              disabled={runningBenchmark}
              className="px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 text-teal-400" />
              {runningBenchmark
                ? 'Running Tesseract Benchmark...'
                : 'Measure OCR Accuracy on 3 Fixtures'}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 pt-2 border-t border-slate-100 items-end">
          {/* Select Mother */}
          <div className="lg:col-span-3">
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              1. Select Mother
            </label>
            <select
              value={selectedMotherId}
              onChange={(e) => setSelectedMotherId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm font-medium bg-white"
            >
              {mothers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.phone})
                </option>
              ))}
            </select>
          </div>

          {/* Standard Upload (JPG, PNG, WEBP, PDF) */}
          <form onSubmit={handleFileUpload} className="lg:col-span-5 flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                2. Upload Scan (JPG, PNG, WEBP, PDF ≤5MB)
              </label>
              <input
                type="file"
                name="file"
                accept="image/jpeg,image/png,image/webp,application/pdf"
                required
                className="w-full text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-teal-50 file:text-teal-800 file:font-semibold border border-slate-300 rounded-lg p-1"
              />
            </div>
            <button
              type="submit"
              disabled={uploading || !selectedMotherId}
              className="px-4 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 shrink-0 cursor-pointer"
            >
              <Upload className="w-3.5 h-3.5" />
              Upload & OCR
            </button>
          </form>

          {/* 3 Synthetic Fixture Test Buttons */}
          <div className="lg:col-span-4">
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Or Load Synthetic ANC Sample Fixture:
            </label>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                disabled={uploading}
                onClick={() => handleLoadSyntheticFixture('printed_clear', 'png')}
                className="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 cursor-pointer"
              >
                #1 Printed PNG
              </button>
              <button
                type="button"
                disabled={uploading}
                onClick={() => handleLoadSyntheticFixture('printed_clear', 'pdf')}
                className="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-200 cursor-pointer"
              >
                #1 Printed PDF
              </button>
              <button
                type="button"
                disabled={uploading}
                onClick={() => handleLoadSyntheticFixture('partially_handwritten', 'png')}
                className="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 cursor-pointer"
              >
                #2 Handwritten/Conflict
              </button>
              <button
                type="button"
                disabled={uploading}
                onClick={() => handleLoadSyntheticFixture('difficult_incomplete', 'png')}
                className="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-800 border border-rose-200 cursor-pointer"
              >
                #3 Difficult/Incomplete
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Optional Live OCR Benchmark Report Panel */}
      {benchmarkData && (
        <div className="bg-slate-900 text-slate-100 rounded-2xl p-5 border border-slate-700 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
                Measured Open-Source OCR Evaluation ({benchmarkData.engine})
              </span>
              <h3 className="text-base font-bold text-white">
                Overall Present-Field Extraction Accuracy:{' '}
                <span className="text-teal-300">
                  {benchmarkData.overall_present_field_accuracy_percent}%
                </span>{' '}
                ({benchmarkData.total_matched_present_fields}/
                {benchmarkData.total_expected_present_fields} fields across 3 synthetic fixtures)
              </h3>
            </div>
            <button
              type="button"
              onClick={() => setBenchmarkData(null)}
              className="text-xs text-slate-400 hover:text-white underline cursor-pointer"
            >
              Close Report
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            {(benchmarkData.fixtures || []).map((fx: any) => (
              <div
                key={fx.fixture_id}
                className="p-3 rounded-xl bg-slate-800 border border-slate-700 space-y-1"
              >
                <div className="font-bold text-teal-300">{fx.title}</div>
                <div>
                  Field Accuracy: <strong>{fx.field_accuracy_percent}%</strong> (
                  {fx.present_fields_matched}/{fx.present_fields_expected}) · Mean Conf:{' '}
                  <strong>{fx.mean_confidence}%</strong>
                </div>
                <div className="text-slate-400">
                  Missing detected: {(fx.missing_fields_detected || []).join(', ') || 'None'} ·
                  Conflicts: {(fx.conflicts_detected || []).length}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Document Version History Tabs for Selected Mother */}
      {motherDocs.length > 0 && (
        <div className="bg-white rounded-xl p-3.5 border border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold uppercase text-slate-500 flex items-center gap-1 mr-1">
              <Layers className="w-3.5 h-3.5 text-teal-700" />
              Document Versions ({motherDocs.length}):
            </span>
            {motherDocs.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setSelectedDocId(d.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                  selectedDocId === d.id
                    ? 'bg-teal-700 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                <span>v{d.version_number || 1}</span>
                <span className="truncate max-w-[140px]">{d.filename}</span>
                <span
                  className={`px-1.5 py-0.2 rounded text-[10px] ${
                    d.confirmed
                      ? 'bg-emerald-500/20 text-emerald-100 border border-emerald-400/40'
                      : 'bg-amber-500/20 text-amber-900'
                  }`}
                >
                  {d.confirmed ? 'CONFIRMED' : 'UNCONFIRMED'}
                </span>
              </button>
            ))}
          </div>
          {activeDoc && (
            <div className="text-xs text-slate-500 font-mono">
              Engine: <strong>{activeDoc.ocr_engine}</strong> · Status:{' '}
              <strong>{activeDoc.ocr_status}</strong> · Mean Conf:{' '}
              <strong>{activeDoc.ocr_job?.mean_confidence ?? '—'}%</strong>
            </div>
          )}
        </div>
      )}

      {/* Main Split-Screen Evidence-Linked Verification Workspace */}
      {activeDoc ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT PANE: Scanned ANC Card + Interactive Bounding Box Overlay */}
          <div className="lg:col-span-6 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3 lg:sticky lg:top-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                  <Eye className="w-4 h-4 text-teal-700" />
                  Scanned ANC Card Source ({activeDoc.filename} · v{activeDoc.version_number})
                </h3>
                <p className="text-[11px] text-slate-500">
                  Click any highlighted region on the scan or select a field on the right to inspect
                  OCR bounding-box coordinates.
                </p>
              </div>
              <a
                href={`/api/documents/${activeDoc.id}/file`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-teal-700 hover:underline font-semibold flex items-center gap-1"
              >
                <Download className="w-3.5 h-3.5" />
                Original ({activeDoc.content_type.split('/')[1]?.toUpperCase()})
              </a>
            </div>

            {/* Scan Canvas with SVG Bounding Box Overlay */}
            <div className="relative w-full rounded-xl overflow-hidden border-2 border-slate-300 bg-slate-100">
              {previewBlobUrl ? (
                <div className="relative w-full">
                  <img
                    src={previewBlobUrl}
                    alt={activeDoc.filename}
                    className="w-full h-auto block select-none"
                  />
                  <svg
                    viewBox={`0 0 ${imgW} ${imgH}`}
                    className="absolute inset-0 w-full h-full pointer-events-auto"
                  >
                    {/* All extracted field bounding boxes */}
                    {fields.map((f) => {
                      if (
                        f.bbox_x === null ||
                        f.bbox_y === null ||
                        f.bbox_w === null ||
                        f.bbox_h === null
                      ) {
                        return null;
                      }
                      const isSelected = selectedField?.field_key === f.field_key;
                      const strokeColor = isSelected
                        ? '#0284c7'
                        : f.conflict_detected
                        ? '#dc2626'
                        : f.uncertainty_flag
                        ? '#d97706'
                        : '#0d9488';
                      return (
                        <g
                          key={f.id}
                          onClick={() => setSelectedFieldKey(f.field_key)}
                          className="cursor-pointer"
                        >
                          <rect
                            x={Math.max(0, f.bbox_x - 6)}
                            y={Math.max(0, f.bbox_y - 4)}
                            width={f.bbox_w + 12}
                            height={f.bbox_h + 8}
                            fill={
                              isSelected
                                ? 'rgba(2, 132, 199, 0.22)'
                                : 'rgba(13, 148, 136, 0.06)'
                            }
                            stroke={strokeColor}
                            strokeWidth={isSelected ? 4 : 2}
                            strokeDasharray={isSelected ? undefined : '5,3'}
                            rx={4}
                          />
                        </g>
                      );
                    })}

                    {/* Individual OCR word token boxes for the currently selected field */}
                    {(selectedField?.source_locations || []).map((loc) => (
                      <rect
                        key={loc.id}
                        x={loc.x}
                        y={loc.y}
                        width={loc.width}
                        height={loc.height}
                        fill="rgba(245, 158, 11, 0.20)"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        rx={2}
                      />
                    ))}
                  </svg>
                </div>
              ) : (
                <div className="p-12 text-center text-xs text-slate-500">
                  Loading authenticated scan preview...
                </div>
              )}
            </div>

            {/* Selected Field Source Provenance Metadata */}
            {selectedField && (
              <div className="p-3 rounded-xl bg-sky-50 border border-sky-200 text-xs space-y-1">
                <div className="flex items-center justify-between font-bold text-sky-950">
                  <span>Selected Field Provenance: {selectedField.field_label}</span>
                  <span className="font-mono">
                    {selectedField.bbox_x !== null
                      ? `bbox=(x:${selectedField.bbox_x}, y:${selectedField.bbox_y}, w:${selectedField.bbox_w}, h:${selectedField.bbox_h})`
                      : 'No bounding box (Field missing on card)'}
                  </span>
                </div>
                <div className="text-sky-900 font-mono truncate">
                  Verbatim OCR Line: {selectedField.source_snippet || '—'}
                </div>
              </div>
            )}

            {/* Verbatim Raw OCR Text Collapsible/Editable */}
            <div>
              <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                Full Verbatim OCR Text ({activeDoc.ocr_job?.word_count || 0} words)
              </label>
              <textarea
                rows={4}
                value={editedRawText}
                onChange={(e) => setEditedRawText(e.target.value)}
                className="w-full p-2.5 rounded-lg border border-slate-300 text-xs font-mono bg-slate-50"
              />
            </div>
          </div>

          {/* RIGHT PANE: Structured Administrative Fields & Human Verification Decisions */}
          <div className="lg:col-span-6 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3">
              <div>
                <h3 className="font-bold text-slate-900 text-base">
                  Extracted Administrative Fields ({fields.length})
                </h3>
                <p className="text-xs text-slate-500">
                  Accept, correct, reject, or mark illegible fields. Missing values are never
                  inferred.
                </p>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold ${
                  activeDoc.confirmed
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                    : 'bg-amber-100 text-amber-900 border border-amber-300'
                }`}
              >
                {activeDoc.confirmed ? 'CONFIRMED RECORD' : 'UNCONFIRMED — AWAITING REVIEW'}
              </span>
            </div>

            {activeDoc.ocr_status === 'failed' && (
              <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-900 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-700" />
                <span>
                  <strong>OCR Processing Error:</strong> {activeDoc.ocr_error}. Please transcribe
                  fields manually using the &ldquo;Manual / Illegible&rdquo; or &ldquo;Correct&rdquo;
                  controls below.
                </span>
              </div>
            )}

            {/* Field Cards */}
            <div className="space-y-3 max-h-[680px] overflow-y-auto pr-1">
              {fields.map((f) => {
                const isSelected = selectedField?.field_key === f.field_key;
                const statusBadge = {
                  unreviewed: 'bg-slate-100 text-slate-700',
                  accepted: 'bg-emerald-100 text-emerald-800',
                  corrected: 'bg-sky-100 text-sky-800',
                  rejected: 'bg-red-100 text-red-800',
                  illegible_manual: 'bg-purple-100 text-purple-800',
                }[f.verification_status];

                return (
                  <div
                    key={f.id}
                    onClick={() => setSelectedFieldKey(f.field_key)}
                    className={`p-3.5 rounded-xl border transition cursor-pointer ${
                      isSelected
                        ? 'border-sky-600 bg-sky-50/40 ring-2 ring-sky-500/20'
                        : f.conflict_detected
                        ? 'border-red-300 bg-red-50/20'
                        : f.uncertainty_flag
                        ? 'border-amber-300 bg-amber-50/20'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-slate-900">{f.field_label}</span>
                        <span className="text-[11px] font-mono text-slate-400">
                          ({f.field_key})
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {f.confidence !== null ? (
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded font-mono font-semibold ${
                              f.confidence >= 80
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            Conf: {f.confidence}%
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded bg-red-100 text-red-800 font-semibold">
                            Missing on Card
                          </span>
                        )}
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full font-bold uppercase ${statusBadge}`}
                        >
                          {f.verification_status.replace('_', ' ')}
                        </span>
                      </div>
                    </div>

                    {/* Uncertainty or Conflict Banner */}
                    {(f.uncertainty_flag || f.conflict_detected) && (
                      <div
                        className={`mt-2 p-2 rounded-lg text-xs flex items-start gap-1.5 ${
                          f.conflict_detected
                            ? 'bg-red-100/80 text-red-900 border border-red-200'
                            : 'bg-amber-100/70 text-amber-900 border border-amber-200'
                        }`}
                      >
                        <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                        <div>
                          <strong>
                            {f.conflict_detected ? 'Conflict Detected: ' : 'Uncertainty Flag: '}
                          </strong>
                          {f.uncertainty_reason || 'Requires human verification'}
                          {f.conflicting_values && f.conflicting_values.length > 1 && (
                            <div className="mt-0.5 font-mono text-[11px]">
                              Candidates: {f.conflicting_values.join(' | ')}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Extracted vs Normalized vs Confirmed Comparison */}
                    <div className="grid grid-cols-3 gap-2 mt-2.5 text-xs bg-white p-2 rounded-lg border border-slate-200/80">
                      <div>
                        <span className="text-[10px] uppercase text-slate-400 block">
                          Extracted Raw
                        </span>
                        <span className="font-mono font-medium text-slate-800">
                          {f.extracted_value ?? '—'}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase text-slate-400 block">
                          Normalized
                        </span>
                        <span className="font-mono font-medium text-teal-800">
                          {f.normalized_value ?? '—'}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase text-slate-400 block">
                          Verified Value
                        </span>
                        <span className="font-mono font-bold text-sky-900">
                          {f.final_value ?? 'Unverified'}
                        </span>
                      </div>
                    </div>

                    {/* Staff Verification Controls */}
                    {canVerify && (
                      <div
                        className="mt-3 pt-2.5 border-t border-slate-200/70 space-y-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={fieldEdits[f.id] ?? ''}
                            onChange={(e) =>
                              setFieldEdits((prev) => ({
                                ...prev,
                                [f.id]: e.target.value,
                              }))
                            }
                            placeholder="Enter corrected or manual value..."
                            className="flex-1 px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs font-mono bg-white"
                          />
                          <input
                            type="text"
                            value={fieldNotes[f.id] ?? ''}
                            onChange={(e) =>
                              setFieldNotes((prev) => ({
                                ...prev,
                                [f.id]: e.target.value,
                              }))
                            }
                            placeholder="Reviewer note (optional)"
                            className="w-40 px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                          />
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleFieldDecision(f, 'accepted')}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <Check className="w-3 h-3" />
                            Accept
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFieldDecision(f, 'corrected')}
                            className="px-2.5 py-1 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <Edit3 className="w-3 h-3" />
                            Save Correction
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFieldDecision(f, 'illegible_manual')}
                            className="px-2.5 py-1 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <HelpCircle className="w-3 h-3" />
                            Mark Illegible / Manual
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFieldDecision(f, 'rejected')}
                            className="px-2.5 py-1 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <Ban className="w-3 h-3" />
                            Reject Field
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Save Confirmed Administrative Record */}
            {canVerify && (
              <div className="pt-3 border-t border-slate-200 flex items-center justify-between gap-4">
                <p className="text-xs text-slate-500">
                  Confirming saves a verified administrative version snapshot and generates reviewable
                  change proposals for any differences against the patient profile.
                </p>
                <button
                  type="button"
                  onClick={handleConfirmDocument}
                  className="px-5 py-2.5 bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold rounded-xl shadow flex items-center gap-2 shrink-0 cursor-pointer"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Save Confirmed Administrative Record
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-2xl p-10 text-center border border-slate-200 text-slate-500 text-sm">
          No ANC card scans uploaded for this mother yet. Upload a scan or click one of the 3
          synthetic ANC card fixture buttons above to begin verification.
        </div>
      )}

      {/* Bottom Section: Administrative Change Proposals & Cross-Version Comparison */}
      {activeDoc && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Administrative Change Proposals Queue */}
          <div className="lg:col-span-6 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <GitCompare className="w-4 h-4 text-amber-600" />
              Administrative Change Proposals ({(activeDoc.change_proposals || []).length})
            </h3>
            <p className="text-xs text-slate-500">
              Confirmed document fields that differ from existing patient records require explicit
              approval before updating the mother&apos;s profile. Follow-up dates never automatically
              replace doctor-authorised care plans.
            </p>
            <div className="space-y-2.5">
              {(activeDoc.change_proposals || []).map((cp) => (
                <div
                  key={cp.id}
                  className="p-3 rounded-xl border border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <div className="font-bold text-slate-900">
                      {cp.field_key.replace('_', ' ').toUpperCase()} ·{' '}
                      <span className="text-[11px] font-normal text-slate-500">
                        ({cp.proposal_type})
                      </span>
                    </div>
                    <div className="mt-1 font-mono">
                      Prior: <span className="text-slate-500">{cp.previous_value || 'None'}</span> →
                      Proposed: <strong className="text-teal-800">{cp.proposed_value}</strong>
                    </div>
                    {cp.reviewed_by && (
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Reviewed by {cp.reviewed_by} ({cp.reviewed_by_role}) at{' '}
                        {cp.reviewed_at ? new Date(cp.reviewed_at).toLocaleString() : ''}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {cp.status === 'pending' && canVerify ? (
                      <>
                        <button
                          type="button"
                          onClick={() => handleProposalDecision(cp.id, 'approved')}
                          className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg cursor-pointer"
                        >
                          Approve Change
                        </button>
                        <button
                          type="button"
                          onClick={() => handleProposalDecision(cp.id, 'rejected')}
                          className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-lg cursor-pointer"
                        >
                          Reject
                        </button>
                      </>
                    ) : (
                      <span
                        className={`px-2.5 py-1 rounded-full font-bold uppercase ${
                          cp.status === 'approved'
                            ? 'bg-emerald-100 text-emerald-800'
                            : cp.status === 'rejected'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {cp.status}
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {(activeDoc.change_proposals || []).length === 0 && (
                <p className="text-xs text-slate-400 py-3">
                  No pending administrative change proposals for this document version.
                </p>
              )}
            </div>
          </div>

          {/* Version & Patient Record Comparison Table */}
          <div className="lg:col-span-6 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h3 className="font-bold text-slate-900 text-sm">
              Cross-Version & Authoritative Record Comparison
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 uppercase">
                    <th className="py-2 px-2">Field</th>
                    <th className="py-2 px-2">Patient Profile</th>
                    <th className="py-2 px-2">Prior Version</th>
                    <th className="py-2 px-2">This Scan (Raw)</th>
                    <th className="py-2 px-2">Verified Final</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {(activeDoc.version_comparison || []).map((row) => (
                    <tr
                      key={row.field_key}
                      className={row.differs_from_confirmed ? 'bg-amber-50/70' : ''}
                    >
                      <td className="py-2 px-2 font-sans font-semibold text-slate-800">
                        {row.field_label}
                      </td>
                      <td className="py-2 px-2 text-slate-600">
                        {row.current_patient_record ?? '—'}
                      </td>
                      <td className="py-2 px-2 text-slate-500">
                        {row.previous_confirmed_version ?? '—'}
                      </td>
                      <td className="py-2 px-2 text-slate-800">{row.document_extracted ?? '—'}</td>
                      <td className="py-2 px-2 font-bold text-teal-800">
                        {row.document_final ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

