export type RoleType = 'admin' | 'doctor' | 'nurse' | 'field_coordinator' | 'asha';

export interface StaffMember {
  id: string;
  name: string;
  email: string | null;
  role: RoleType;
  normalized_role: 'admin' | 'doctor' | 'nurse' | 'field_coordinator';
  clinic: string;
  phone: string;
  is_active: boolean;
  created_at: string;
}

export interface Mother {
  id: string;
  name: string;
  phone: string;
  patient_identifier?: string;
  age: number | null;
  edd: string | null;
  lmp: string | null;
  address: string;
  language: 'te' | 'hi' | 'en';
  consent: boolean;
  consent_updated_at: string | null;
  notes: string;
  clinic: string;
  registered_by: string;
  created_at: string;
  next_visit_date?: string | null;
  appointment_status?: string | null;
}

export interface CarePlan {
  id: string;
  mother_id: string;
  clinic: string;
  visit_date: string;
  visit_type: string;
  appointment_status: 'scheduled' | 'completed' | 'missed' | 'rescheduled' | 'cancelled';
  follow_up_notes: string;
  note: string;
  version: number;
  approved_by: string;
  created_at: string;
  active: boolean;
  mother_name?: string;
  mother_phone?: string;
  mother_consent?: boolean;
  is_overdue?: boolean;
}

export interface TaskItem {
  id: string;
  mother_id: string;
  mother_name?: string;
  clinic: string;
  category: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  due_date: string | null;
  status: 'open' | 'in_progress' | 'resolved' | 'cancelled';
  assigned_to: string;
  assigned_to_name?: string;
  detail: string;
  completion_notes: string;
  completed_at: string | null;
  created_by: string;
  created_at: string;
}

export interface MessageItem {
  id: string;
  mother_id: string;
  mother_name?: string;
  clinic: string;
  direction: 'outbound' | 'inbound';
  body: string;
  status: string;
  provider: string;
  sent_at: string;
}

export interface TransportItem {
  id: string;
  mother_id: string;
  mother_name?: string;
  mother_phone?: string;
  clinic: string;
  date: string;
  pickup_time: string;
  from_location: string;
  destination: string;
  status: 'requested' | 'assigned' | 'in_transit' | 'completed' | 'cancelled';
  partner: string;
  vehicle_notes: string;
  requested_by: string;
  created_at: string;
}

export interface ExpenseItem {
  id: string;
  clinic: string;
  category: string;
  amount_paise: number;
  amount_rupees: number;
  description: string;
  receipt_ref: string;
  approved: boolean;
  created_by: string;
  approved_by: string;
  created_at: string;
}

export interface FieldSourceLocationItem {
  id: string;
  extracted_field_id: string;
  document_id: string;
  page_number: number;
  x: number;
  y: number;
  width: number;
  height: number;
  token_text: string;
  token_confidence: number;
}

export type FieldVerificationStatus =
  | 'unreviewed'
  | 'accepted'
  | 'corrected'
  | 'rejected'
  | 'illegible_manual';

export interface ExtractedFieldItem {
  id: string;
  document_id: string;
  field_key: string;
  field_label: string;
  extracted_value: string | null;
  normalized_value: string | null;
  confidence: number | null;
  uncertainty_flag: boolean;
  uncertainty_reason: string;
  conflict_detected: boolean;
  conflicting_values: string[];
  source_page: number;
  bbox_x: number | null;
  bbox_y: number | null;
  bbox_w: number | null;
  bbox_h: number | null;
  source_snippet: string;
  verification_status: FieldVerificationStatus;
  final_value: string | null;
  reviewer_note: string;
  verified_by: string;
  verified_at: string | null;
  source_locations: FieldSourceLocationItem[];
}

export interface OcrJobItem {
  id: string;
  document_id: string;
  engine: string;
  external_provider_used: boolean;
  status: string;
  duration_ms: number;
  word_count: number;
  mean_confidence: number | null;
  missing_fields: string[];
  conflicts: Array<{
    field_key: string;
    type: string;
    values?: string[];
    previous_value?: string;
    extracted_value?: string;
    message: string;
  }>;
  error_message: string;
}

export interface DocumentVersionSummary {
  id: string;
  version_number: number;
  filename: string;
  ocr_status: string;
  confirmed: boolean;
  review_status: string;
  confirmed_by: string;
  confirmed_at: string | null;
  created_at: string | null;
}

export interface VersionComparisonRow {
  field_key: string;
  field_label: string;
  current_patient_record: string | null;
  previous_confirmed_version: string | null;
  document_extracted: string | null;
  document_normalized: string | null;
  document_final: string | null;
  differs_from_confirmed: boolean;
}

export interface AdminChangeProposalItem {
  id: string;
  mother_id: string;
  document_id: string;
  clinic: string;
  field_key: string;
  previous_value: string | null;
  proposed_value: string;
  proposal_type: 'mother_profile_update' | 'appointment_schedule_note';
  status: 'pending' | 'approved' | 'rejected';
  reviewed_by: string | null;
  reviewed_by_role: string | null;
  review_note: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface VerificationDecisionItem {
  id: string;
  document_id: string;
  extracted_field_id: string | null;
  field_key: string;
  decision: string;
  extracted_value: string | null;
  final_value: string | null;
  notes: string;
  decided_by: string;
  decided_by_role: string;
  decided_at: string;
}

export interface DocumentItem {
  id: string;
  mother_id: string;
  mother_name?: string;
  mother_phone?: string;
  clinic: string;
  version_number: number;
  supersedes_document_id: string | null;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  image_width: number;
  image_height: number;
  page_count: number;
  ocr_status: string;
  ocr_engine: string;
  ocr_error: string;
  extracted_text: string;
  structured_fields: string;
  confirmed: boolean;
  review_status: string;
  uploaded_by: string;
  confirmed_by: string;
  confirmed_at: string | null;
  created_at: string;
  ocr_job?: OcrJobItem | null;
  fields?: ExtractedFieldItem[];
  versions?: DocumentVersionSummary[];
  version_comparison?: VersionComparisonRow[];
  change_proposals?: AdminChangeProposalItem[];
  decisions?: VerificationDecisionItem[];
}

export interface AuditEvent {
  id: string;
  clinic: string;
  actor: string;
  actor_role: string;
  action: string;
  entity: string;
  entity_id: string;
  occurred: string;
  detail: string;
}

export interface ClinicAnalytics {
  clinic: string;
  registered_mothers: number;
  consented_mothers: number;
  active_care_plans: number;
  upcoming_appointments: number;
  overdue_plans: number;
  open_tasks: number;
  messages: number;
  transport_requests: number;
  documents_total: number;
  documents_confirmed: number;
  documents_unconfirmed: number;
  pending_change_proposals?: number;
  tasks_by_status: Record<string, number>;
  tasks_by_priority: Record<string, number>;
  transport_by_status: Record<string, number>;
  expenses_total_paise: number;
  expenses_approved_paise: number;
  expenses_pending_paise: number;
  expenses_by_category: Record<string, number>;
  staff_by_role: Record<string, number>;
}
