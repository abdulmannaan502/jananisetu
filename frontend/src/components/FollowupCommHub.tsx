import React, { useEffect, useState, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Send,
  PhoneCall,
  ShieldAlert,
  Settings,
  UserCheck,
  Inbox,
  Play,
  RotateCcw,
  XCircle,
  Clock,
  ArrowRight,
  Stethoscope,
  Activity,
} from 'lucide-react';
import { apiRequest } from '../api';
import type { Mother, CarePlan, TaskItem, MessageItem, StaffMember } from '../types';

interface Props {
  currentUser: StaffMember;
  mothers: Mother[];
  appointments: CarePlan[];
  tasks: TaskItem[];
  messages: MessageItem[];
  onRefreshParent: () => Promise<void>;
  notify: (text: string, type?: 'success' | 'error') => void;
}

type SubView =
  | 'closed_loop'
  | 'reminder_queue'
  | 'delivery_monitor'
  | 'staff_inbox'
  | 'human_followup'
  | 'caregivers'
  | 'settings';

const STATE_BADGES: Record<string, string> = {
  scheduled: 'bg-slate-100 text-slate-800 border-slate-300',
  reminder_sent: 'bg-sky-100 text-sky-800 border-sky-300',
  delivered: 'bg-indigo-100 text-indigo-800 border-indigo-300',
  acknowledged: 'bg-teal-100 text-teal-800 border-teal-300',
  visit_confirmed: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  closed: 'bg-slate-800 text-white border-slate-900',
  delivery_failed: 'bg-red-100 text-red-800 border-red-300',
  no_acknowledgement: 'bg-amber-100 text-amber-800 border-amber-300',
  contact_required: 'bg-orange-100 text-orange-800 border-orange-300',
  staff_assigned: 'bg-purple-100 text-purple-800 border-purple-300',
  contact_attempted: 'bg-blue-100 text-blue-800 border-blue-300',
  missed_appointment: 'bg-rose-100 text-rose-800 border-rose-300',
  rescheduled_by_authorised_staff: 'bg-cyan-100 text-cyan-800 border-cyan-300',
  unreachable: 'bg-red-200 text-red-900 border-red-400',
  resolved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
};

export default function FollowupCommHub({
  currentUser,
  mothers,
  appointments,
  tasks,
  messages,
  onRefreshParent,
  notify,
}: Props) {
  const [subView, setSubView] = useState<SubView>('closed_loop');
  const [reminderJobs, setReminderJobs] = useState<any[]>([]);
  const [workerHealth, setWorkerHealth] = useState<any>(null);
  const [stateMachineSpec, setStateMachineSpec] = useState<{
    states: string[];
    allowed_transitions: Record<string, string[]>;
  } | null>(null);
  const [inboxMessages, setInboxMessages] = useState<any[]>([]);
  const [selectedMotherId, setSelectedMotherId] = useState<string>(mothers[0]?.id || '');
  const [caregivers, setCaregivers] = useState<any[]>([]);
  const [commConfig, setCommConfig] = useState<any>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');
  const [contactAttempts, setContactAttempts] = useState<any[]>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<boolean>(false);

  const userRole = currentUser.normalized_role;

  const loadPhase4Data = useCallback(async () => {
    try {
      const [jobsRes, healthRes, smRes, inboxRes, cfgRes] = await Promise.all([
        apiRequest<any[]>('/api/reminders/jobs'),
        apiRequest<any>('/api/worker/health'),
        apiRequest<any>('/api/appointments/state-machine'),
        apiRequest<any[]>('/api/messages/inbox'),
        apiRequest<any>('/api/settings/communication'),
      ]);
      setReminderJobs(jobsRes);
      setWorkerHealth(healthRes);
      setStateMachineSpec(smRes);
      setInboxMessages(inboxRes);
      setCommConfig(cfgRes);
    } catch (err: any) {
      notify(err.message || 'Failed to load communication engine state', 'error');
    }
  }, [notify]);

  useEffect(() => {
    loadPhase4Data();
  }, [loadPhase4Data]);

  useEffect(() => {
    if (!selectedMotherId && mothers.length > 0) {
      setSelectedMotherId(mothers[0].id);
    }
  }, [mothers, selectedMotherId]);

  const loadCaregivers = useCallback(async () => {
    if (!selectedMotherId) return;
    try {
      const res = await apiRequest<any[]>(`/api/mothers/${selectedMotherId}/caregivers`);
      setCaregivers(res);
    } catch {
      setCaregivers([]);
    }
  }, [selectedMotherId]);

  useEffect(() => {
    loadCaregivers();
  }, [loadCaregivers]);

  const loadContactAttempts = useCallback(async (tid: string) => {
    if (!tid) {
      setContactAttempts([]);
      return;
    }
    try {
      const res = await apiRequest<any[]>(`/api/tasks/${tid}/contact-attempts`);
      setContactAttempts(res);
    } catch {
      setContactAttempts([]);
    }
  }, []);

  useEffect(() => {
    if (!selectedTaskId && tasks.length > 0) {
      setSelectedTaskId(tasks[0].id);
    }
  }, [tasks, selectedTaskId]);

  useEffect(() => {
    if (selectedTaskId) {
      loadContactAttempts(selectedTaskId);
    }
  }, [selectedTaskId, loadContactAttempts]);

  const handleRunWorker = async (simulateFailure = false, evaluateOverdue = false) => {
    setBusy(true);
    try {
      const res = await apiRequest<any>('/api/reminders/worker/run', 'POST', {
        force_due: true,
        simulate_failure: simulateFailure,
        evaluate_overdue: evaluateOverdue,
      });
      notify(
        `Worker executed: ${res.jobs_sent} sent, ${res.jobs_retrying} retrying, ${res.jobs_dead_lettered} dead-lettered`
      );
      await loadPhase4Data();
      await onRefreshParent();
    } catch (err: any) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const deadLetterJobs = reminderJobs.filter(
    (j) => j.status === 'dead_letter' || j.status === 'retrying'
  );

  return (
    <div className="space-y-6">
      {/* Top Status & Worker Health Bar */}
      <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-md flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-teal-500/20 text-teal-300 border border-teal-500/30">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold">
                Phase 4: Closed-Loop Maternal Follow-Up &amp; Communication Engine
              </h2>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-teal-500/20 text-teal-300 font-semibold border border-teal-400/30">
                Asia/Kolkata (IST)
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-0.5">
              Transactional Outbox · Idempotent Scheduling · Signed Webhooks · Human Escalation ·
              Caregiver Privacy Guard
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => handleRunWorker(false, false)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 text-xs font-bold transition cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            Dispatch Due Reminders Now
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => handleRunWorker(true, false)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-600/80 hover:bg-amber-600 text-xs font-semibold transition cursor-pointer"
            title="Simulate provider failure to test exponential backoff and dead-letter queue"
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            Simulate Provider Failure
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              try {
                const futureIso = new Date(Date.now() + 24 * 3600 * 1000).toISOString();
                const res = await apiRequest<any>(
                  `/api/reminders/evaluate-overdue?as_of_iso=${encodeURIComponent(futureIso)}`,
                  'POST'
                );
                notify(
                  `Escalated ${res.plans_escalated} unacknowledged plan(s); created ${res.tasks_created} follow-up task(s)`
                );
                await loadPhase4Data();
                await onRefreshParent();
              } catch (err: any) {
                notify(err.message, 'error');
              }
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-xs font-semibold transition cursor-pointer"
          >
            <Clock className="w-3.5 h-3.5" />
            Escalate Unacknowledged Deadlines
          </button>
        </div>
      </div>

      {/* Queue Metrics Summary Cards */}
      {workerHealth && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">Pending Queue</div>
            <div className="text-2xl font-bold text-slate-900 mt-0.5">
              {workerHealth.queue_metrics?.pending_jobs ?? 0}
            </div>
            <div className="text-[11px] text-slate-400">Scheduled IST offsets</div>
          </div>
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">Sent Jobs</div>
            <div className="text-2xl font-bold text-teal-700 mt-0.5">
              {workerHealth.queue_metrics?.sent_jobs ?? 0}
            </div>
            <div className="text-[11px] text-slate-400">Dispatched via adapter</div>
          </div>
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">Retrying</div>
            <div className="text-2xl font-bold text-amber-600 mt-0.5">
              {workerHealth.queue_metrics?.retrying_jobs ?? 0}
            </div>
            <div className="text-[11px] text-slate-400">Exponential backoff</div>
          </div>
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">Dead-Letter</div>
            <div className="text-2xl font-bold text-red-600 mt-0.5">
              {workerHealth.queue_metrics?.dead_letter_jobs ?? 0}
            </div>
            <div className="text-[11px] text-slate-400">Awaiting operator retry</div>
          </div>
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">Cancelled</div>
            <div className="text-2xl font-bold text-slate-600 mt-0.5">
              {workerHealth.queue_metrics?.cancelled_jobs ?? 0}
            </div>
            <div className="text-[11px] text-slate-400">Superseded / Opt-out</div>
          </div>
          <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase">WhatsApp Mode</div>
            <div className="text-xs font-bold text-slate-800 mt-1.5 truncate">
              {workerHealth.messaging_providers?.whatsapp_cloud?.operational
                ? 'Live Cloud API'
                : 'Local Simulator Active'}
            </div>
            <div className="text-[10px] text-slate-400">
              {workerHealth.messaging_providers?.whatsapp_cloud?.operational
                ? 'Verified credentials'
                : 'Live creds not configured'}
            </div>
          </div>
        </div>
      )}

      {/* Sub-navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {[
          { id: 'closed_loop', label: '1. Closed-Loop Workflow', icon: CheckCircle2 },
          {
            id: 'reminder_queue',
            label: `2. Reminder Queue & Dead-Letter (${reminderJobs.length})`,
            icon: Bell,
          },
          {
            id: 'delivery_monitor',
            label: `3. Message Delivery Monitor (${messages.length})`,
            icon: Send,
          },
          {
            id: 'staff_inbox',
            label: `4. Staff Inbox & Clinician Review (${inboxMessages.length})`,
            icon: Inbox,
          },
          {
            id: 'human_followup',
            label: '5. Human Follow-Up & Contact Attempts',
            icon: PhoneCall,
          },
          {
            id: 'caregivers',
            label: '6. Caregiver Permissions & Privacy',
            icon: UserCheck,
          },
          { id: 'settings', label: '7. Clinic Comm Settings & Health', icon: Settings },
        ].map((t) => {
          const Icon = t.icon;
          const active = subView === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubView(t.id as SubView)}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
                active
                  ? 'bg-teal-700 text-white shadow-xs'
                  : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* =====================================================================
          VIEW 1: CLOSED-LOOP STATE MACHINE WORKFLOW
         ===================================================================== */}
      {subView === 'closed_loop' && (
        <div className="space-y-4">
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs">
            <h3 className="font-bold text-slate-900 text-sm mb-2">
              Closed-Loop Appointment State Machine
            </h3>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 bg-slate-50 p-3 rounded-xl border border-slate-200">
              <span className="px-2.5 py-1 rounded-lg bg-slate-200 font-bold text-slate-800">
                Scheduled
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="px-2.5 py-1 rounded-lg bg-sky-100 font-bold text-sky-800">
                Reminder Sent
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="px-2.5 py-1 rounded-lg bg-indigo-100 font-bold text-indigo-800">
                Delivered
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="px-2.5 py-1 rounded-lg bg-teal-100 font-bold text-teal-800">
                Acknowledged
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="px-2.5 py-1 rounded-lg bg-emerald-100 font-bold text-emerald-800">
                Visit Confirmed
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="px-2.5 py-1 rounded-lg bg-slate-800 font-bold text-white">
                Closed
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Delivery, patient acknowledgement, clinic attendance confirmation, and loop closure are
              strictly distinct states. Asynchronous events are idempotent and invalid transitions are
              rejected.
            </p>
          </div>

          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs">
            <h3 className="font-bold text-slate-900 mb-4">
              Active Doctor-Authorised Care Plans ({appointments.filter((a) => a.active).length})
            </h3>
            <div className="space-y-3">
              {appointments
                .filter((a) => a.active)
                .map((cp: any) => {
                  const currentState = cp.followup_state || 'scheduled';
                  const allowedNext =
                    stateMachineSpec?.allowed_transitions?.[currentState] || [];
                  return (
                    <div
                      key={cp.id}
                      className="p-4 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-4 hover:border-teal-300 transition"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm text-slate-900">
                            {cp.mother_name || cp.mother_id}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                            Visit: {cp.visit_date} (v{cp.version})
                          </span>
                          <span
                            className={`text-xs px-2.5 py-0.5 rounded-full font-bold border ${
                              STATE_BADGES[currentState] || 'bg-slate-100 text-slate-800'
                            }`}
                          >
                            State: {currentState}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600">{cp.note || 'Routine ANC checkup'}</p>
                        <div className="text-[11px] text-slate-400 flex flex-wrap gap-3">
                          <span>Plan ID: {cp.id}</span>
                          {cp.ack_deadline_at && <span>Ack Deadline: {cp.ack_deadline_at}</span>}
                          {cp.acknowledged_at && <span>Acknowledged: {cp.acknowledged_at}</span>}
                          {cp.visit_confirmed_at && (
                            <span>Visit Confirmed: {cp.visit_confirmed_at}</span>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              const res = await apiRequest<any>(
                                `/api/reminders/schedule/${cp.id}`,
                                'POST'
                              );
                              notify(
                                `Verified ${res.scheduled_jobs_count} idempotent reminder job(s) for plan ${cp.id}`
                              );
                              await loadPhase4Data();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="px-2.5 py-1.5 rounded-lg border border-teal-300 text-teal-800 bg-teal-50 hover:bg-teal-100 text-xs font-semibold cursor-pointer"
                        >
                          Sync Reminders
                        </button>

                        {allowedNext.map((nextSt) => (
                          <button
                            key={nextSt}
                            type="button"
                            onClick={async () => {
                              try {
                                await apiRequest(`/api/appointments/${cp.id}/transition`, 'POST', {
                                  target_state: nextSt,
                                  reason: `Manual transition by ${currentUser.name}`,
                                });
                                notify(`Transitioned appointment ${cp.id} → ${nextSt}`);
                                await loadPhase4Data();
                                await onRefreshParent();
                              } catch (err: any) {
                                notify(err.message, 'error');
                              }
                            }}
                            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold cursor-pointer"
                          >
                            → {nextSt.replace(/_/g, ' ')}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 2: REMINDER QUEUE & DEAD-LETTER RECOVERY
         ===================================================================== */}
      {subView === 'reminder_queue' && (
        <div className="space-y-6">
          {deadLetterJobs.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-2xl p-5">
              <div className="flex items-center gap-2 text-red-900 font-bold text-sm mb-3">
                <AlertTriangle className="w-4 h-4 text-red-600" />
                Failed-Delivery Recovery &amp; Dead-Letter Queue ({deadLetterJobs.length})
              </div>
              <div className="space-y-2">
                {deadLetterJobs.map((job) => (
                  <div
                    key={job.id}
                    className="bg-white p-3.5 rounded-xl border border-red-200 flex flex-wrap items-center justify-between gap-3"
                  >
                    <div>
                      <div className="text-xs font-bold text-slate-900">
                        {job.mother_name} · Offset {job.offset_hours}h ·{' '}
                        <span className="text-red-700 uppercase">{job.status}</span> (Attempts:{' '}
                        {job.attempts}/{job.max_attempts})
                      </div>
                      <div className="text-[11px] text-red-600 mt-0.5">
                        Last Error: {job.last_error || 'Provider timeout'}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        Idempotency Key: {job.idempotency_key}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await apiRequest(`/api/reminders/jobs/${job.id}/retry`, 'POST', {
                            channel_override: 'local-simulator',
                          });
                          notify(`Operator retried job ${job.id} successfully`);
                          await loadPhase4Data();
                          await onRefreshParent();
                        } catch (err: any) {
                          notify(err.message, 'error');
                        }
                      }}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-700 hover:bg-red-800 text-white text-xs font-bold cursor-pointer"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Operator Retry Now
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-bold text-slate-900">
                  Persistent Appointment Reminder Queue ({reminderJobs.length})
                </h3>
                <p className="text-xs text-slate-500">
                  Backed by TransactionalOutbox and unique idempotency keys. Obsolete jobs are
                  automatically cancelled when a CarePlan is superseded or consent is withdrawn.
                </p>
              </div>
              <button
                type="button"
                onClick={loadPhase4Data}
                className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer"
              >
                <RefreshCw className="w-4 h-4 text-slate-600" />
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 uppercase">
                    <th className="py-2.5 pr-3">Mother / Recipient</th>
                    <th className="py-2.5 pr-3">Visit Date</th>
                    <th className="py-2.5 pr-3">Offset</th>
                    <th className="py-2.5 pr-3">Scheduled (UTC/IST)</th>
                    <th className="py-2.5 pr-3">Status</th>
                    <th className="py-2.5 pr-3">Attempts</th>
                    <th className="py-2.5 pr-3">Idempotency Key</th>
                    <th className="py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {reminderJobs.map((j) => (
                    <tr key={j.id} className="hover:bg-slate-50">
                      <td className="py-2.5 pr-3 font-semibold text-slate-900">
                        {j.mother_name || j.mother_id}
                        <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 uppercase">
                          {j.recipient_type}
                        </span>
                        {j.caregiver_name && (
                          <div className="text-[10px] text-teal-700">CG: {j.caregiver_name}</div>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">{j.visit_date || '—'}</td>
                      <td className="py-2.5 pr-3 font-mono">{j.offset_hours}h</td>
                      <td className="py-2.5 pr-3 text-slate-600">
                        {j.scheduled_for?.slice(0, 19).replace('T', ' ')}
                      </td>
                      <td className="py-2.5 pr-3">
                        <span
                          className={`px-2 py-0.5 rounded-full font-bold text-[10px] uppercase ${
                            j.status === 'sent'
                              ? 'bg-emerald-100 text-emerald-800'
                              : j.status === 'dead_letter'
                              ? 'bg-red-100 text-red-800'
                              : j.status === 'retrying'
                              ? 'bg-amber-100 text-amber-800'
                              : j.status === 'cancelled'
                              ? 'bg-slate-100 text-slate-500 line-through'
                              : 'bg-sky-100 text-sky-800'
                          }`}
                        >
                          {j.status}
                        </span>
                        {j.cancellation_reason && (
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            {j.cancellation_reason}
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        {j.attempts}/{j.max_attempts}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[10px] text-slate-400 max-w-[180px] truncate">
                        {j.idempotency_key}
                      </td>
                      <td className="py-2.5 text-right">
                        {(j.status === 'pending' || j.status === 'retrying') && (
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                await apiRequest(`/api/reminders/jobs/${j.id}/cancel`, 'POST');
                                notify(`Cancelled reminder job ${j.id}`);
                                await loadPhase4Data();
                              } catch (err: any) {
                                notify(err.message, 'error');
                              }
                            }}
                            className="text-red-600 hover:underline font-semibold cursor-pointer"
                          >
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 3: MESSAGE DELIVERY MONITOR & CALLBACK SIMULATOR
         ===================================================================== */}
      {subView === 'delivery_monitor' && (
        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
          <div>
            <h3 className="font-bold text-slate-900">
              Message Delivery Status Tracking &amp; Ordering Guard ({messages.length})
            </h3>
            <p className="text-xs text-slate-500">
              Tracks provider message IDs, masked phone numbers, and enforces monotonic status
              ordering (queued → sent → delivered → read → acknowledged). Out-of-order callbacks
              never downgrade higher states.
            </p>
          </div>

          <div className="divide-y divide-slate-100 text-sm">
            {messages.map((msg: any) => (
              <div
                key={msg.id}
                className="py-3.5 flex flex-wrap items-start justify-between gap-4"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                        msg.direction === 'outbound'
                          ? 'bg-teal-100 text-teal-800'
                          : 'bg-indigo-100 text-indigo-800'
                      }`}
                    >
                      {msg.direction} ({msg.recipient_type || 'mother'})
                    </span>
                    <span className="font-bold text-slate-900">
                      {msg.mother_name || msg.mother_id}
                    </span>
                    {msg.recipient_phone_masked && (
                      <span className="text-xs font-mono text-slate-500">
                        {msg.recipient_phone_masked}
                      </span>
                    )}
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 font-semibold text-slate-700">
                      Status: {msg.status} (rank {msg.delivery_status_rank ?? 0})
                    </span>
                  </div>
                  <p className="text-slate-700 text-xs">{msg.body}</p>
                  <div className="text-[11px] text-slate-400 flex flex-wrap gap-3">
                    <span>Provider: {msg.provider}</span>
                    {msg.provider_message_id && <span>WAMID: {msg.provider_message_id}</span>}
                    {msg.template_name && <span>Template: {msg.template_name}</span>}
                    {msg.failure_code && (
                      <span className="text-red-600 font-semibold">
                        Failure: {msg.failure_code} ({msg.failure_reason})
                      </span>
                    )}
                  </div>
                </div>

                {msg.direction === 'outbound' && (
                  <div className="flex items-center gap-1.5">
                    {(['delivered', 'read', 'failed'] as const).map((st) => (
                      <button
                        key={st}
                        type="button"
                        onClick={async () => {
                          try {
                            const res = await apiRequest<any>(
                              `/api/messages/${msg.id}/simulate-callback`,
                              'POST',
                              {
                                event_id: `evt-ui-${msg.id}-${st}-${Date.now()}`,
                                delivery_status: st,
                              }
                            );
                            notify(
                              `Callback '${st}' processed (status_updated=${res.status_updated}, current=${res.message_status})`
                            );
                            await loadPhase4Data();
                            await onRefreshParent();
                          } catch (err: any) {
                            notify(err.message, 'error');
                          }
                        }}
                        className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-slate-700 cursor-pointer"
                      >
                        Callback: {st}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 4: STAFF INBOX & CLINICIAN PROTOCOL REVIEW
         ===================================================================== */}
      {subView === 'staff_inbox' && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs">
            <h3 className="font-bold text-slate-900 mb-1">
              Simulate Inbound Patient Reply (YES / STOP / Clinical Concern)
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              Replies are preserved verbatim. &apos;YES&apos; acknowledges the appointment;
              &apos;STOP&apos; immediately withdraws consent and cancels pending reminders; other
              messages are flagged for human clinician review under clinic protocol without
              autonomous AI severity scoring.
            </p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                const mid = String(fd.get('mother_id') || '');
                const body = String(fd.get('body') || '');
                try {
                  await apiRequest('/api/messages/reply', 'POST', { mother_id: mid, body });
                  e.currentTarget.reset();
                  notify('Verbatim inbound reply recorded');
                  await loadPhase4Data();
                  await onRefreshParent();
                } catch (err: any) {
                  notify(err.message, 'error');
                }
              }}
              className="grid grid-cols-1 md:grid-cols-12 gap-3 text-sm"
            >
              <select
                name="mother_id"
                required
                className="md:col-span-3 px-3 py-2 rounded-lg border border-slate-300"
              >
                {mothers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <input
                name="body"
                required
                placeholder="Type verbatim patient message (e.g., 'YES' or 'I have swelling and headache')"
                className="md:col-span-7 px-3 py-2 rounded-lg border border-slate-300"
              />
              <button
                type="submit"
                className="md:col-span-2 py-2 bg-indigo-700 hover:bg-indigo-800 text-white font-semibold rounded-lg cursor-pointer"
              >
                Record Reply
              </button>
            </form>
          </div>

          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
            <div className="flex items-center gap-2">
              <Stethoscope className="w-5 h-5 text-teal-700" />
              <h3 className="font-bold text-slate-900">
                Inbound Patient Inbox &amp; Clinician Protocol Review ({inboxMessages.length})
              </h3>
            </div>
            <div className="space-y-3">
              {inboxMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`p-4 rounded-xl border ${
                    msg.flagged_for_clinical_review &&
                    msg.clinical_review_status !== 'reviewed_by_clinician'
                      ? 'border-amber-300 bg-amber-50/50'
                      : 'border-slate-200 bg-white'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-slate-900">
                        {msg.mother_name || msg.mother_id}
                      </span>
                      {msg.flagged_for_clinical_review && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold border border-amber-300">
                          Flagged for Clinician Protocol Review ({msg.clinical_review_status})
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-400">{msg.sent_at?.slice(0, 19)}</span>
                  </div>
                  <p className="text-sm text-slate-800 font-medium mt-2 bg-white p-3 rounded-lg border border-slate-200">
                    &ldquo;{msg.body}&rdquo;
                  </p>

                  {msg.clinical_review_note && (
                    <div className="mt-2 text-xs text-emerald-800 bg-emerald-50 p-2.5 rounded-lg border border-emerald-200">
                      <strong>Clinician Protocol Note ({msg.reviewed_by}):</strong>{' '}
                      {msg.clinical_review_note}
                    </div>
                  )}

                  {(userRole === 'doctor' || userRole === 'nurse') &&
                    msg.clinical_review_status !== 'reviewed_by_clinician' && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <input
                          type="text"
                          value={reviewNotes[msg.id] || ''}
                          onChange={(e) =>
                            setReviewNotes((prev) => ({ ...prev, [msg.id]: e.target.value }))
                          }
                          placeholder="Enter clinician protocol review note (no autonomous AI scoring)..."
                          className="flex-1 min-w-[240px] px-3 py-1.5 text-xs rounded-lg border border-slate-300 bg-white"
                        />
                        <button
                          type="button"
                          onClick={async () => {
                            const note =
                              reviewNotes[msg.id] ||
                              'Reviewed under clinic ANC protocol; contacted patient.';
                            try {
                              await apiRequest(`/api/messages/${msg.id}/review`, 'PATCH', {
                                clinical_review_note: note,
                                resolve_related_task: true,
                              });
                              notify('Clinician protocol review recorded');
                              await loadPhase4Data();
                              await onRefreshParent();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="px-3 py-1.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold cursor-pointer"
                        >
                          Save Clinician Protocol Review
                        </button>
                      </div>
                    )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 5: HUMAN FOLLOW-UP TASK BOARD & CONTACT ATTEMPTS
         ===================================================================== */}
      {subView === 'human_followup' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4 h-fit">
            <h3 className="font-bold text-slate-900">Record Staff Contact Attempt</h3>
            <p className="text-xs text-slate-500">
              Log outreach attempts by nurses or field coordinators and escalate unresolved tasks to
              a clinic supervisor.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Select Follow-Up Task *
              </label>
              <select
                value={selectedTaskId}
                onChange={(e) => setSelectedTaskId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
              >
                {tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    [{t.status.toUpperCase()}] {t.mother_name || t.mother_id} — {t.category} (
                    {t.priority})
                  </option>
                ))}
              </select>
            </div>

            {selectedTaskId && (
              <>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      const res = await apiRequest<any>(
                        `/api/tasks/${selectedTaskId}/contact-attempts`,
                        'POST',
                        {
                          channel: String(fd.get('channel') || 'phone_call'),
                          outcome: String(fd.get('outcome') || 'reached_confirmed'),
                          notes: String(fd.get('notes') || ''),
                        }
                      );
                      e.currentTarget.reset();
                      notify(
                        `Contact attempt logged (task=${res.task_status}, plan=${res.care_plan_followup_state})`
                      );
                      await loadContactAttempts(selectedTaskId);
                      await loadPhase4Data();
                      await onRefreshParent();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Outreach Channel
                      </label>
                      <select
                        name="channel"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      >
                        <option value="phone_call">Phone Call</option>
                        <option value="home_visit">Home Visit (ASHA/ANM)</option>
                        <option value="whatsapp_followup">WhatsApp Follow-up</option>
                        <option value="asha_liaison">Community Liaison</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Outcome
                      </label>
                      <select
                        name="outcome"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      >
                        <option value="reached_confirmed">Reached &amp; Confirmed</option>
                        <option value="no_answer">No Answer</option>
                        <option value="busy">Line Busy</option>
                        <option value="reschedule_requested">Reschedule Requested</option>
                        <option value="wrong_number">Wrong Number</option>
                        <option value="unreachable">Unreachable</option>
                      </select>
                    </div>
                  </div>
                  <textarea
                    name="notes"
                    rows={2}
                    placeholder="Record outcome notes (e.g. Spoke with mother, confirmed morning transport)..."
                    className="w-full px-3 py-2 rounded-lg border border-slate-300"
                  />
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg cursor-pointer"
                  >
                    Record Contact Attempt
                  </button>
                </form>

                <div className="pt-3 border-t border-slate-200">
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await apiRequest(`/api/tasks/${selectedTaskId}/escalate`, 'POST', {
                          escalation_reason:
                            'Unresolved operational follow-up; escalated to clinic supervisor for review.',
                        });
                        notify(`Task ${selectedTaskId} escalated to supervisor (priority=urgent)`);
                        await onRefreshParent();
                      } catch (err: any) {
                        notify(err.message, 'error');
                      }
                    }}
                    className="w-full py-2 bg-rose-50 hover:bg-rose-100 text-rose-800 border border-rose-200 font-bold text-xs rounded-lg cursor-pointer"
                  >
                    Escalate Task to Clinic Supervisor
                  </button>
                </div>
              </>
            )}
          </div>

          <div className="lg:col-span-7 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
            <h3 className="font-bold text-slate-900">
              Contact Attempt History for Selected Task ({contactAttempts.length})
            </h3>
            {contactAttempts.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">
                No contact attempts logged yet for this task.
              </p>
            ) : (
              <div className="space-y-3">
                {contactAttempts.map((ca) => (
                  <div key={ca.id} className="p-3.5 rounded-xl border border-slate-200">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-slate-900">
                        {ca.channel.replace(/_/g, ' ').toUpperCase()} →{' '}
                        <span className="text-teal-700">{ca.outcome}</span>
                      </span>
                      <span className="text-slate-400">{ca.attempted_at?.slice(0, 19)}</span>
                    </div>
                    <p className="text-xs text-slate-600 mt-1">{ca.notes || 'No notes'}</p>
                    <div className="text-[11px] text-slate-400 mt-1">
                      Logged by: {ca.staff_name || ca.staff_id} ({ca.staff_role})
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 6: CAREGIVER PERMISSIONS & PRIVACY BOUNDARY
         ===================================================================== */}
      {subView === 'caregivers' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4 h-fit">
            <div className="flex items-center gap-2 text-teal-800 font-bold text-sm">
              <ShieldAlert className="w-4 h-4" />
              Caregiver Permission &amp; Privacy Guard
            </div>
            <p className="text-xs text-slate-500">
              Caregivers only receive limited administrative appointment reminders when explicitly
              permitted. ANC scans, OCR results, and clinical findings are strictly blocked from
              caregiver channels.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Select Mother
              </label>
              <select
                value={selectedMotherId}
                onChange={(e) => setSelectedMotherId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
              >
                {mothers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.phone})
                  </option>
                ))}
              </select>
            </div>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                try {
                  await apiRequest(`/api/mothers/${selectedMotherId}/caregivers`, 'POST', {
                    caregiver_name: String(fd.get('caregiver_name') || ''),
                    caregiver_phone: String(fd.get('caregiver_phone') || ''),
                    relationship_type: String(fd.get('relationship_type') || 'spouse'),
                    language: String(fd.get('language') || 'te'),
                    consent_granted: true,
                    allow_admin_reminders: true,
                  });
                  e.currentTarget.reset();
                  notify('Caregiver permission recorded and administrative reminder scheduled');
                  await loadCaregivers();
                  await loadPhase4Data();
                } catch (err: any) {
                  notify(err.message, 'error');
                }
              }}
              className="space-y-3 text-sm"
            >
              <input
                name="caregiver_name"
                required
                placeholder="Caregiver Full Name *"
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  name="caregiver_phone"
                  required
                  placeholder="Phone (10 digits) *"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300"
                />
                <select
                  name="relationship_type"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300"
                >
                  <option value="spouse">Spouse</option>
                  <option value="mother">Mother</option>
                  <option value="mother_in_law">Mother-in-Law</option>
                  <option value="sister">Sister</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <button
                type="submit"
                className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg cursor-pointer"
              >
                Grant Caregiver Administrative Permission
              </button>
            </form>
          </div>

          <div className="lg:col-span-7 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
            <h3 className="font-bold text-slate-900">
              Registered Caregivers for Selected Mother ({caregivers.length})
            </h3>
            {caregivers.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">
                No caregivers registered for this mother.
              </p>
            ) : (
              <div className="space-y-3">
                {caregivers.map((cg) => (
                  <div
                    key={cg.id}
                    className="p-4 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-3"
                  >
                    <div>
                      <div className="font-bold text-sm text-slate-900">
                        {cg.caregiver_name} ({cg.relationship_type})
                      </div>
                      <div className="text-xs text-slate-500">
                        Phone: {cg.caregiver_phone} · Permission:{' '}
                        <strong
                          className={cg.consent_granted ? 'text-emerald-700' : 'text-red-600'}
                        >
                          {cg.consent_granted ? 'Granted (Admin Reminders Only)' : 'Revoked'}
                        </strong>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {cg.consent_granted && (
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              await apiRequest(`/api/caregivers/${cg.id}/send-reminder`, 'POST', {});
                              notify('Administrative-only reminder sent to caregiver');
                              await loadPhase4Data();
                              await onRefreshParent();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="px-3 py-1.5 rounded-lg bg-teal-50 text-teal-800 border border-teal-200 text-xs font-bold cursor-pointer"
                        >
                          Send Admin Reminder
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const res = await apiRequest<any>(`/api/caregivers/${cg.id}`, 'PATCH', {
                              consent_granted: !cg.consent_granted,
                            });
                            notify(
                              cg.consent_granted
                                ? `Caregiver permission revoked (${res.cancelled_reminder_jobs} pending job(s) cancelled)`
                                : 'Caregiver permission re-granted'
                            );
                            await loadCaregivers();
                            await loadPhase4Data();
                          } catch (err: any) {
                            notify(err.message, 'error');
                          }
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer ${
                          cg.consent_granted
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {cg.consent_granted ? 'Revoke Permission' : 'Restore Permission'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 7: CLINIC COMMUNICATION SETTINGS & PROVIDER HEALTH
         ===================================================================== */}
      {subView === 'settings' && commConfig && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
            <h3 className="font-bold text-slate-900">
              Clinic Reminder Offsets &amp; Retry Policy ({currentUser.clinic})
            </h3>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                const rawOffsets = String(fd.get('offsets') || '-48,-24,0')
                  .split(',')
                  .map((s) => parseInt(s.trim(), 10))
                  .filter((n) => !Number.isNaN(n));
                try {
                  const updated = await apiRequest<any>('/api/settings/communication', 'PUT', {
                    timezone: 'Asia/Kolkata',
                    reminder_offsets_hours: rawOffsets.length ? rawOffsets : [-48, -24, 0],
                    ack_deadline_hours: Number(fd.get('ack_deadline_hours') || 12),
                    default_channel: String(fd.get('default_channel') || 'local-simulator'),
                    whatsapp_template_en: commConfig.whatsapp_template_en,
                    whatsapp_template_te: commConfig.whatsapp_template_te,
                    whatsapp_template_hi: commConfig.whatsapp_template_hi,
                    max_retry_attempts: Number(fd.get('max_retry_attempts') || 3),
                    retry_base_seconds: Number(fd.get('retry_base_seconds') || 60),
                    enable_caregiver_reminders: true,
                  });
                  setCommConfig(updated);
                  notify('Clinic communication settings updated');
                } catch (err: any) {
                  notify(err.message, 'error');
                }
              }}
              className="space-y-3 text-sm"
            >
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  Reminder Offsets in Hours (relative to 09:00 IST on visit date)
                </label>
                <input
                  name="offsets"
                  defaultValue={(commConfig.reminder_offsets_hours || [-48, -24, 0]).join(', ')}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 font-mono"
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    Ack Deadline (h)
                  </label>
                  <input
                    name="ack_deadline_hours"
                    type="number"
                    defaultValue={commConfig.ack_deadline_hours || 12}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    Max Retries
                  </label>
                  <input
                    name="max_retry_attempts"
                    type="number"
                    defaultValue={commConfig.max_retry_attempts || 3}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    Backoff Base (s)
                  </label>
                  <input
                    name="retry_base_seconds"
                    type="number"
                    defaultValue={commConfig.retry_base_seconds || 60}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  Default Messaging Adapter
                </label>
                <select
                  name="default_channel"
                  defaultValue={commConfig.default_channel || 'local-simulator'}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300"
                >
                  <option value="local-simulator">Local Simulator (Deterministic Testing)</option>
                  <option value="whatsapp-cloud">Meta WhatsApp Cloud API</option>
                  <option value="sms-gateway">SMS Gateway Provider</option>
                </select>
              </div>
              {(userRole === 'admin' || userRole === 'doctor') && (
                <button
                  type="submit"
                  className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg cursor-pointer"
                >
                  Save Clinic Communication Configuration
                </button>
              )}
            </form>
          </div>

          <div className="lg:col-span-6 bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
            <h3 className="font-bold text-slate-900">
              Messaging Provider &amp; Worker Infrastructure Status
            </h3>
            <div className="space-y-3 text-xs">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <div className="font-bold text-slate-900">
                  Worker Engine: {workerHealth?.worker_engine}
                </div>
                <div className="text-slate-600 mt-1">{workerHealth?.redis_note}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <div className="font-bold text-slate-900">
                  Meta WhatsApp Cloud API:{' '}
                  <span
                    className={
                      commConfig.providers_status?.whatsapp_cloud?.operational
                        ? 'text-emerald-700'
                        : 'text-amber-700'
                    }
                  >
                    {commConfig.providers_status?.whatsapp_cloud?.mode}
                  </span>
                </div>
                <div className="text-slate-600 mt-1">
                  {commConfig.providers_status?.whatsapp_cloud?.note}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

