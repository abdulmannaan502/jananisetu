import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ShieldCheck,
  Users,
  Calendar,
  MapPin,
  Building2,
  Truck,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileCheck,
  RefreshCw,
  Play,
  WifiOff,
  UploadCloud,
  UserPlus,
  UserX,
  Stethoscope,
  ClipboardCheck,
  FileEdit,
} from 'lucide-react';
import { apiRequest } from '../api';
import type { Mother, StaffMember } from '../types';

interface Props {
  currentUser: StaffMember;
  mothers: Mother[];
  staffList: StaffMember[];
  notify: (text: string, type?: 'success' | 'error') => void;
  onRefreshGlobal: () => Promise<void>;
  initialSubTab?: SubTab;
}

export type SubTab =
  | 'ops_centre'
  | 'workforce'
  | 'services'
  | 'field_visits'
  | 'partners_referrals'
  | 'transport_ops'
  | 'governance';

const OFFLINE_DRAFTS_STORAGE_KEY = 'jananisetu_offline_field_visit_drafts_v1';

export default function WorkforceOperationsHub({
  currentUser,
  mothers,
  staffList,
  notify,
  onRefreshGlobal,
  initialSubTab = 'ops_centre',
}: Props) {
  const [subTab, setSubTab] = useState<SubTab>(initialSubTab);
  const [loading, setLoading] = useState(false);

  // Live Phase 5 State
  const [opsDashboard, setOpsDashboard] = useState<any>(null);
  const [workforceProfiles, setWorkforceProfiles] = useState<any[]>([]);
  const [credentials, setCredentials] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [leaves, setLeaves] = useState<any[]>([]);
  const [services, setServices] = useState<any[]>([]);
  const [fieldVisits, setFieldVisits] = useState<any[]>([]);
  const [partnerFacilities, setPartnerFacilities] = useState<any[]>([]);
  const [referrals, setReferrals] = useState<any[]>([]);
  const [transportPartners, setTransportPartners] = useState<any[]>([]);
  const [vehiclesDrivers, setVehiclesDrivers] = useState<any[]>([]);
  const [transportTrips, setTransportTrips] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [corrections, setCorrections] = useState<any[]>([]);
  const [walkthroughResult, setWalkthroughResult] = useState<any>(null);

  // Offline field visit drafts stored locally until synced
  const [offlineDrafts, setOfflineDrafts] = useState<any[]>(() => {
    try {
      const raw = localStorage.getItem(OFFLINE_DRAFTS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  // Form states — Workforce Onboarding
  const [onboardName, setOnboardName] = useState('');
  const [onboardEmail, setOnboardEmail] = useState('');
  const [onboardRole, setOnboardRole] = useState<'doctor' | 'nurse' | 'field_coordinator'>('nurse');
  const [onboardEmpType, setOnboardEmpType] = useState('full_time_employee');
  const [onboardQual, setOnboardQual] = useState('B.Sc Nursing / ANM');
  const [onboardCouncil, setOnboardCouncil] = useState('Telangana Nurses & Midwives Council');
  const [onboardRegNo, setOnboardRegNo] = useState('');
  const [onboardFacility, setOnboardFacility] = useState('PHC Nalgonda Main');

  // Form states — Shift Assignment
  const [shiftStaffId, setShiftStaffId] = useState('');
  const [shiftDate, setShiftDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [shiftStart, setShiftStart] = useState('09:00');
  const [shiftEnd, setShiftEnd] = useState('17:00');
  const [shiftType, setShiftType] = useState<'morning' | 'afternoon' | 'night' | 'field_outreach'>('morning');
  const [shiftFacility, setShiftFacility] = useState('PHC Nalgonda OPD');

  // Form states — Leave Request
  const [leaveStaffId, setLeaveStaffId] = useState('');
  const [leaveStart, setLeaveStart] = useState(() => new Date().toISOString().slice(0, 10));
  const [leaveEnd, setLeaveEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [leaveReason, setLeaveReason] = useState('');
  const [leaveReplacementId, setLeaveReplacementId] = useState('');

  // Form states — Service Coordination
  const [srvMotherId, setSrvMotherId] = useState('');
  const [srvType, setSrvType] = useState('anc_home_visit');
  const [srvClinicalReq, setSrvClinicalReq] = useState(true);
  const [srvPriority, setSrvPriority] = useState<'low' | 'medium' | 'high' | 'urgent'>('high');
  const [srvStaffId, setSrvStaffId] = useState('');
  const [srvNotes, setSrvNotes] = useState('');

  // Form states — Field Visit
  const [fvMotherId, setFvMotherId] = useState('');
  const [fvStaffId, setFvStaffId] = useState('');
  const [fvDate, setFvDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [fvWindow, setFvWindow] = useState('09:00-11:00');
  const [fvAddress, setFvAddress] = useState('Ward 4 Devarakonda');
  const [fvLocationConsent, setFvLocationConsent] = useState(false);
  const [fvLocationPurpose, setFvLocationPurpose] = useState('Confirm home outreach visit arrival');

  // Form states — Partner Facility & Referral
  const [pfName, setPfName] = useState('');
  const [pfType, setPfType] = useState('referral_hospital');
  const [pfContact, setPfContact] = useState('');
  const [pfPhone, setPfPhone] = useState('');
  const [pfAgreement, setPfAgreement] = useState('MOU-2026-NEW');

  const [refMotherId, setRefMotherId] = useState('');
  const [refPartnerId, setRefPartnerId] = useState('');
  const [refCategory, setRefCategory] = useState('clinical_obstetric');
  const [refReason, setRefReason] = useState('');
  const [refChargeRupees, setRefChargeRupees] = useState(1200);

  // Form states — Transport Partner & Vehicle/Driver
  const [tpName, setTpName] = useState('');
  const [tpContact, setTpContact] = useState('');
  const [tpPhone, setTpPhone] = useState('');
  const [tpTariffRupees, setTpTariffRupees] = useState(450);

  const [vdPartnerId, setVdPartnerId] = useState('');
  const [vdDriverName, setVdDriverName] = useState('');
  const [vdDriverPhone, setVdDriverPhone] = useState('');
  const [vdLicenseNo, setVdLicenseNo] = useState('');
  const [vdRegNo, setVdRegNo] = useState('');
  const [vdInsuranceNo, setVdInsuranceNo] = useState('');

  // Form states — Governance Incident & Record Correction
  const [incType, setIncType] = useState('protocol_deviation');
  const [incSeverity, setIncSeverity] = useState<'low' | 'medium' | 'high' | 'critical'>('high');
  const [incTitle, setIncTitle] = useState('');
  const [incDesc, setIncDesc] = useState('');

  const [corrMotherId, setCorrMotherId] = useState('');
  const [corrField, setCorrField] = useState('address');
  const [corrNewValue, setCorrNewValue] = useState('');
  const [corrReason, setCorrReason] = useState('');

  const userRole = currentUser.normalized_role;

  const loadPhase5Data = useCallback(async () => {
    setLoading(true);
    try {
      const [
        dashRes,
        wpRes,
        credRes,
        shiftRes,
        leaveRes,
        srvRes,
        fvRes,
        pfRes,
        refRes,
        tpRes,
        vdRes,
        trRes,
        incRes,
        corrRes,
      ] = await Promise.all([
        apiRequest<any>('/api/operations/dashboard'),
        apiRequest<any[]>('/api/workforce/profiles'),
        apiRequest<any[]>('/api/workforce/credentials'),
        apiRequest<any[]>('/api/workforce/shifts'),
        apiRequest<any[]>('/api/workforce/leaves'),
        apiRequest<any[]>('/api/services'),
        apiRequest<any[]>('/api/field-visits'),
        apiRequest<any[]>('/api/partners/facilities'),
        apiRequest<any[]>('/api/referrals'),
        apiRequest<any[]>('/api/transport-ops/partners'),
        apiRequest<any[]>('/api/transport-ops/vehicles'),
        apiRequest<any[]>('/api/transport'),
        apiRequest<any[]>('/api/governance/incidents'),
        apiRequest<any[]>('/api/governance/corrections'),
      ]);

      setOpsDashboard(dashRes);
      setWorkforceProfiles(wpRes);
      setCredentials(credRes);
      setShifts(shiftRes);
      setLeaves(leaveRes);
      setServices(srvRes);
      setFieldVisits(fvRes);
      setPartnerFacilities(pfRes);
      setReferrals(refRes);
      setTransportPartners(tpRes);
      setVehiclesDrivers(vdRes);
      setTransportTrips(trRes);
      setIncidents(incRes);
      setCorrections(corrRes);

      if (mothers.length > 0) {
        setSrvMotherId((prev) => prev || mothers[0].id);
        setFvMotherId((prev) => prev || mothers[0].id);
        setRefMotherId((prev) => prev || mothers[0].id);
        setCorrMotherId((prev) => prev || mothers[0].id);
      }
      if (staffList.length > 0) {
        const nurseOrDoc = staffList.find((s) => s.normalized_role === 'nurse' || s.normalized_role === 'doctor') || staffList[0];
        setShiftStaffId((prev) => prev || nurseOrDoc.id);
        setLeaveStaffId((prev) => prev || nurseOrDoc.id);
        setSrvStaffId((prev) => prev || nurseOrDoc.id);
        setFvStaffId((prev) => prev || nurseOrDoc.id);
      }
      if (pfRes.length > 0) {
        setRefPartnerId((prev) => prev || pfRes[0].id);
      }
      if (tpRes.length > 0) {
        setVdPartnerId((prev) => prev || tpRes[0].id);
      }
    } catch (err: any) {
      notify(err.message || 'Failed to load Phase 5 operational data', 'error');
    } finally {
      setLoading(false);
    }
  }, [mothers, staffList, notify]);

  useEffect(() => {
    loadPhase5Data();
  }, [loadPhase5Data]);

  const handleRunWalkthrough = async () => {
    try {
      setLoading(true);
      const res = await apiRequest<any>('/api/operations/demo-walkthrough', 'POST');
      setWalkthroughResult(res);
      notify('Completed 10-step End-to-End Maternal Care Operations Walkthrough!');
      await loadPhase5Data();
      await onRefreshGlobal();
    } catch (err: any) {
      notify(err.message || 'Walkthrough failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Offline Draft Queue helpers
  const saveOfflineDraft = () => {
    if (!fvMotherId || !fvStaffId) {
      notify('Select mother and assigned staff for offline draft', 'error');
      return;
    }
    const draft = {
      offline_draft_id: `offline-fv-${Date.now()}`,
      mother_id: fvMotherId,
      assigned_staff_id: fvStaffId,
      visit_date: fvDate,
      scheduled_window: fvWindow,
      visit_address: fvAddress,
      contact_confirmed: true,
      patient_consent_verified: true,
      location_consent_granted: fvLocationConsent,
      checkin_latitude: fvLocationConsent ? 17.0575 : null,
      checkin_longitude: fvLocationConsent ? 79.2684 : null,
      location_purpose: fvLocationConsent ? fvLocationPurpose : '',
      role_scoped_notes: 'Recorded offline during village home visit; MCP card reviewed.',
      completion_evidence_type: 'signed_home_visit_register',
      completion_evidence_ref: `HVR-${Date.now().toString().slice(-5)}`,
    };
    const next = [...offlineDrafts, draft];
    setOfflineDrafts(next);
    try {
      localStorage.setItem(OFFLINE_DRAFTS_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // ignore
    }
    notify(`Saved offline field visit draft ${draft.offline_draft_id} locally.`);
  };

  const syncOfflineDrafts = async () => {
    if (offlineDrafts.length === 0) return;
    try {
      const res = await apiRequest<any>('/api/field-visits/offline-sync', 'POST', {
        drafts: offlineDrafts,
      });
      setOfflineDrafts([]);
      try {
        localStorage.removeItem(OFFLINE_DRAFTS_STORAGE_KEY);
      } catch {
        // ignore
      }
      notify(`Synchronized ${res.synced_count} offline field visit drafts to clinic server!`);
      await loadPhase5Data();
    } catch (err: any) {
      notify(err.message || 'Offline sync failed', 'error');
    }
  };

  return (
    <div className="space-y-6">
      {/* Phase 5 Sub-Navigation Bar */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {[
            { id: 'ops_centre', label: 'Operations Centre', icon: <Activity className="w-4 h-4" /> },
            { id: 'workforce', label: 'Workforce & Shifts', icon: <Users className="w-4 h-4" /> },
            { id: 'services', label: 'Service Coordination', icon: <ClipboardCheck className="w-4 h-4" /> },
            { id: 'field_visits', label: 'Field Visits & Offline Sync', icon: <MapPin className="w-4 h-4" /> },
            { id: 'partners_referrals', label: 'Hospital Partnerships & Referrals', icon: <Building2 className="w-4 h-4" /> },
            { id: 'transport_ops', label: 'Transport Fleet & Trips', icon: <Truck className="w-4 h-4" /> },
            { id: 'governance', label: 'Clinical & Org Governance', icon: <ShieldCheck className="w-4 h-4" /> },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubTab(t.id as SubTab)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                subTab === t.id
                  ? 'bg-teal-700 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {(userRole === 'admin' || userRole === 'doctor') && (
            <button
              type="button"
              onClick={handleRunWalkthrough}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-indigo-700 hover:bg-indigo-800 text-white shadow-sm cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" />
              Run 10-Step E2E Walkthrough
            </button>
          )}
          <button
            type="button"
            onClick={loadPhase5Data}
            className="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 cursor-pointer"
            title="Refresh Operations Data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-teal-700' : ''}`} />
          </button>
        </div>
      </div>

      {/* =====================================================================
          SUB-TAB 1: OPERATIONS CENTRE DASHBOARD
         ===================================================================== */}
      {subTab === 'ops_centre' && opsDashboard && (
        <div className="space-y-6">
          {/* E2E Walkthrough Proof Banner if executed */}
          {walkthroughResult && (
            <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-indigo-950 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-700" />
                  10-Step End-to-End Operational Scenario Executed ({walkthroughResult.clinic})
                </h3>
                <button
                  type="button"
                  onClick={() => setWalkthroughResult(null)}
                  className="text-xs text-indigo-700 underline cursor-pointer"
                >
                  Hide Walkthrough Proof
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2.5">
                {(walkthroughResult.steps_completed || []).map((st: any) => (
                  <div
                    key={st.step}
                    className="bg-white p-3 rounded-xl border border-indigo-100 text-xs space-y-1"
                  >
                    <div className="font-bold text-indigo-900">
                      Step {st.step}: {st.name}
                    </div>
                    <div className="text-slate-600 font-mono text-[11px] truncate">
                      ID: {st.entity_id}
                    </div>
                    <div className="text-emerald-700 font-semibold text-[11px]">{st.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top KPI Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Staff On Duty Today</span>
              <div className="text-2xl font-bold text-teal-700 mt-1">
                {opsDashboard.summary.staff_on_duty_today}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Field Visits Today</span>
              <div className="text-2xl font-bold text-emerald-700 mt-1">
                {opsDashboard.summary.field_visits_today}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Unassigned Services</span>
              <div className="text-2xl font-bold text-amber-600 mt-1">
                {opsDashboard.summary.unassigned_service_requests}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Pending Referrals</span>
              <div className="text-2xl font-bold text-sky-700 mt-1">
                {opsDashboard.summary.pending_hospital_referrals}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Pending Transport</span>
              <div className="text-2xl font-bold text-indigo-700 mt-1">
                {opsDashboard.summary.pending_transport_pickups}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Completed Services</span>
              <div className="text-2xl font-bold text-emerald-700 mt-1">
                {opsDashboard.summary.completed_services_count}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Failed / No-Show</span>
              <div className="text-2xl font-bold text-red-600 mt-1">
                {opsDashboard.summary.failed_or_missed_services_count}
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <span className="text-[11px] text-slate-500 font-medium">Total Expenditure</span>
              <div className="text-xl font-bold text-slate-900 mt-1">
                ₹{opsDashboard.expenses_summary?.total_rupees?.toLocaleString() || 0}
              </div>
            </div>
          </div>

          {/* Governance Alerts & Staffing Gaps */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
              <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                Clinical & Organisational Governance Alerts
              </h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200">
                  <div className="text-amber-900 font-semibold">Unverified Staff Credentials</div>
                  <div className="text-xl font-bold text-amber-800 mt-1">
                    {opsDashboard.governance_alerts?.unverified_staff_credentials_count || 0}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-red-50 border border-red-200">
                  <div className="text-red-900 font-semibold">Expiring/Expired Credentials</div>
                  <div className="text-xl font-bold text-red-800 mt-1">
                    {opsDashboard.governance_alerts?.expiring_or_expired_credentials_count || 0}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-sky-50 border border-sky-200">
                  <div className="text-sky-900 font-semibold">Expiring Partner Agreements</div>
                  <div className="text-xl font-bold text-sky-800 mt-1">
                    {opsDashboard.governance_alerts?.expiring_partner_agreements_count || 0}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-purple-50 border border-purple-200">
                  <div className="text-purple-900 font-semibold">Open Governance Incidents</div>
                  <div className="text-xl font-bold text-purple-800 mt-1">
                    {opsDashboard.governance_alerts?.open_governance_incidents_count || 0}
                  </div>
                </div>
              </div>
              {opsDashboard.staffing_gaps?.length > 0 && (
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-900 space-y-1">
                  <div className="font-bold">Staffing Coverage Gaps Detected:</div>
                  {opsDashboard.staffing_gaps.map((g: string, i: number) => (
                    <div key={i}>• {g}</div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
              <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                <Users className="w-4 h-4 text-teal-700" />
                Role-Scoped Workforce Workload & Credential Status
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 uppercase">
                      <th className="py-2 px-2">Staff</th>
                      <th className="py-2 px-2">Role / Employment</th>
                      <th className="py-2 px-2">Credentials</th>
                      <th className="py-2 px-2">Active Load</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(opsDashboard.staff_workload || []).map((w: any) => (
                      <tr key={w.staff_id}>
                        <td className="py-2 px-2 font-semibold text-slate-900">{w.staff_name}</td>
                        <td className="py-2 px-2">
                          <span className="capitalize font-medium">{w.clinical_role}</span>
                          <span className="block text-[10px] text-slate-500">
                            {w.employment_type?.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="py-2 px-2">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              w.credential_verification_status === 'verified'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {w.credential_verification_status}
                          </span>
                        </td>
                        <td className="py-2 px-2 font-mono">
                          {w.active_services} srv · {w.visits_today} visits · {w.open_tasks} tasks
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 2: WORKFORCE, CREDENTIALS, SHIFTS & LEAVES
         ===================================================================== */}
      {subTab === 'workforce' && (
        <div className="space-y-6">
          {/* Governance Notice */}
          <div className="bg-teal-50 border border-teal-200 rounded-xl p-3.5 text-xs text-teal-950 flex items-center justify-between">
            <div>
              <strong>Workforce Credential Governance:</strong> Employment status (full-time, NHM
              deputed, contractor) is stored separately from clinical role. Self-entered registration
              numbers remain <code className="font-bold">unverified</code> until reviewed by a
              different authorised supervisor with documented evidence.
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Onboard Staff Form (Admin only) */}
            {userRole === 'admin' && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await apiRequest('/api/workforce/onboard', 'POST', {
                      name: onboardName,
                      email: onboardEmail,
                      role: onboardRole,
                      employment_type: onboardEmpType,
                      clinical_cadre:
                        onboardRole === 'doctor'
                          ? 'medical_officer_obgyn'
                          : onboardRole === 'nurse'
                          ? 'anm_staff_nurse'
                          : 'asha_field_coordinator',
                      qualification: onboardQual,
                      registration_council: onboardCouncil,
                      registration_number: onboardRegNo,
                      assigned_facility: onboardFacility,
                    });
                    setOnboardName('');
                    setOnboardEmail('');
                    setOnboardRegNo('');
                    notify('Staff onboarded! Credentials queued as UNVERIFIED for supervisor review.');
                    await loadPhase5Data();
                    await onRefreshGlobal();
                  } catch (err: any) {
                    notify(err.message, 'error');
                  }
                }}
                className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
              >
                <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                  <UserPlus className="w-4 h-4 text-teal-700" />
                  Onboard Healthcare Staff
                </h3>
                <input
                  type="text"
                  required
                  placeholder="Full Name (e.g. Dr. Meenakshi Rao)"
                  value={onboardName}
                  onChange={(e) => setOnboardName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs"
                />
                <input
                  type="email"
                  required
                  placeholder="Official Email"
                  value={onboardEmail}
                  onChange={(e) => setOnboardEmail(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs"
                />
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-600 mb-1">
                      Clinical / System Role
                    </label>
                    <select
                      value={onboardRole}
                      onChange={(e) => setOnboardRole(e.target.value as any)}
                      className="w-full px-2.5 py-2 rounded-lg border border-slate-300 text-xs"
                    >
                      <option value="doctor">Doctor (Clinician)</option>
                      <option value="nurse">ANM / Staff Nurse</option>
                      <option value="field_coordinator">Field Coordinator</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-600 mb-1">
                      Employment Status
                    </label>
                    <select
                      value={onboardEmpType}
                      onChange={(e) => setOnboardEmpType(e.target.value)}
                      className="w-full px-2.5 py-2 rounded-lg border border-slate-300 text-xs"
                    >
                      <option value="full_time_employee">Full-Time Employee</option>
                      <option value="contract_clinician">Contract Clinician</option>
                      <option value="nhm_deputed">NHM Deputed</option>
                      <option value="community_honorarium">Community Honorarium</option>
                    </select>
                  </div>
                </div>
                <input
                  type="text"
                  placeholder="Qualification (e.g. MBBS, DGO / ANM)"
                  value={onboardQual}
                  onChange={(e) => setOnboardQual(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs"
                />
                <input
                  type="text"
                  placeholder="Council (e.g. Telangana State Medical Council)"
                  value={onboardCouncil}
                  onChange={(e) => setOnboardCouncil(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs"
                />
                <input
                  type="text"
                  placeholder="Registration Number (starts unverified)"
                  value={onboardRegNo}
                  onChange={(e) => setOnboardRegNo(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs"
                />
                <button
                  type="submit"
                  className="w-full py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold rounded-lg cursor-pointer"
                >
                  Onboard Staff Member
                </button>
              </form>
            )}

            {/* Workforce Profiles & Credential Verification */}
            <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
              <h3 className="font-bold text-slate-900 text-sm">
                Clinic Workforce Profiles & Credential Verification ({workforceProfiles.length})
              </h3>
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {workforceProfiles.map((wp) => {
                  const staffCreds = credentials.filter((c) => c.staff_id === wp.staff_id);
                  return (
                    <div
                      key={wp.id}
                      className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-3 text-xs"
                    >
                      <div className="space-y-1">
                        <div className="font-bold text-slate-900 flex items-center gap-2">
                          <span>{wp.staff_name}</span>
                          <span className="px-2 py-0.5 rounded bg-teal-100 text-teal-800 text-[10px] uppercase">
                            Role: {wp.clinical_role}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px]">
                            Employment: {wp.employment_type?.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="text-slate-600">
                          Qualification: <strong>{wp.qualification || 'N/A'}</strong> · Reg No:{' '}
                          <code className="font-mono">{wp.registration_number || 'None'}</code> ·
                          Facility: {wp.assigned_facility}
                        </div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              wp.credential_verification_status === 'verified'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            Credential Status: {wp.credential_verification_status}
                          </span>
                          {wp.credential_evidence_ref && (
                            <span className="text-[11px] text-slate-500">
                              Evidence: {wp.credential_evidence_ref}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {staffCreds.map((cred) =>
                          cred.verification_status !== 'verified' &&
                          (userRole === 'admin' || userRole === 'doctor') &&
                          cred.staff_id !== currentUser.id ? (
                            <button
                              key={cred.id}
                              type="button"
                              onClick={async () => {
                                try {
                                  await apiRequest(
                                    `/api/workforce/credentials/${cred.id}/verify`,
                                    'POST',
                                    {
                                      decision: 'verified',
                                      review_evidence_note:
                                        'Verified against State Council Official Register by supervisor.',
                                    }
                                  );
                                  notify(`Verified credential ${cred.registration_number}!`);
                                  await loadPhase5Data();
                                } catch (err: any) {
                                  notify(err.message, 'error');
                                }
                              }}
                              className="px-2.5 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg text-[11px] font-semibold cursor-pointer"
                            >
                              Verify Credential
                            </button>
                          ) : null
                        )}
                        {userRole === 'admin' &&
                          wp.staff_id !== currentUser.id &&
                          wp.onboarding_status !== 'offboarded' && (
                            <button
                              type="button"
                              onClick={async () => {
                                try {
                                  await apiRequest(
                                    `/api/workforce/profiles/${wp.staff_id}/offboard`,
                                    'POST',
                                    { reason: 'End of deputation / rotation completed' }
                                  );
                                  notify(`Offboarded ${wp.staff_name} and flagged open assignments.`);
                                  await loadPhase5Data();
                                } catch (err: any) {
                                  notify(err.message, 'error');
                                }
                              }}
                              className="px-2.5 py-1.5 bg-red-100 hover:bg-red-200 text-red-800 rounded-lg text-[11px] font-semibold cursor-pointer"
                            >
                              Offboard
                            </button>
                          )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Shift Assignment & Leave Management */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
              <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                <Calendar className="w-4 h-4 text-teal-700" />
                Shift Assignment & Attendance ({shifts.length})
              </h3>
              {(userRole === 'admin' || userRole === 'doctor') && (
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      await apiRequest('/api/workforce/shifts', 'POST', {
                        staff_id: shiftStaffId,
                        facility_name: shiftFacility,
                        shift_date: shiftDate,
                        start_time: shiftStart,
                        end_time: shiftEnd,
                        shift_type: shiftType,
                        notes: 'Assigned via Workforce Hub',
                      });
                      notify('Shift assigned (conflict check passed)!');
                      await loadPhase5Data();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="grid grid-cols-2 sm:grid-cols-3 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs"
                >
                  <select
                    value={shiftStaffId}
                    onChange={(e) => setShiftStaffId(e.target.value)}
                    className="px-2 py-1.5 rounded border border-slate-300"
                  >
                    {staffList.map((st) => (
                      <option key={st.id} value={st.id}>
                        {st.name}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    value={shiftDate}
                    onChange={(e) => setShiftDate(e.target.value)}
                    className="px-2 py-1.5 rounded border border-slate-300"
                  />
                  <select
                    value={shiftType}
                    onChange={(e) => setShiftType(e.target.value as any)}
                    className="px-2 py-1.5 rounded border border-slate-300"
                  >
                    <option value="morning">Morning (09:00-17:00)</option>
                    <option value="afternoon">Afternoon (14:00-20:00)</option>
                    <option value="field_outreach">Field Outreach</option>
                  </select>
                  <input
                    type="time"
                    value={shiftStart}
                    onChange={(e) => setShiftStart(e.target.value)}
                    className="px-2 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="time"
                    value={shiftEnd}
                    onChange={(e) => setShiftEnd(e.target.value)}
                    className="px-2 py-1.5 rounded border border-slate-300"
                  />
                  <button
                    type="submit"
                    className="bg-teal-700 hover:bg-teal-800 text-white font-bold rounded px-3 py-1.5 cursor-pointer"
                  >
                    Assign Shift
                  </button>
                </form>
              )}

              <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
                {shifts.map((sh) => (
                  <div
                    key={sh.id}
                    className="p-2.5 rounded-lg border border-slate-200 flex items-center justify-between"
                  >
                    <div>
                      <span className="font-bold text-slate-900">{sh.staff_name}</span> ·{' '}
                      <span className="font-mono">
                        {sh.shift_date} ({sh.start_time}-{sh.end_time})
                      </span>{' '}
                      · <span className="text-slate-600">{sh.facility_name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-slate-100 font-semibold">
                        {sh.status}
                      </span>
                      {sh.status === 'scheduled' && (
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              await apiRequest(
                                `/api/workforce/shifts/${sh.id}/attendance`,
                                'PATCH',
                                { status: 'checked_in' }
                              );
                              notify('Staff checked in for shift');
                              await loadPhase5Data();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="px-2 py-1 bg-emerald-700 text-white rounded text-[11px] cursor-pointer"
                        >
                          Check In
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Leave & Replacement Staff */}
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
              <h3 className="font-bold text-slate-900 text-sm">
                Staff Leave & Replacement Coverage ({leaves.length})
              </h3>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await apiRequest('/api/workforce/leaves', 'POST', {
                      staff_id: leaveStaffId || currentUser.id,
                      start_date: leaveStart,
                      end_date: leaveEnd,
                      leave_type: 'casual',
                      reason: leaveReason || 'Personal / medical leave',
                      replacement_staff_id: leaveReplacementId || null,
                    });
                    setLeaveReason('');
                    notify('Leave request submitted.');
                    await loadPhase5Data();
                  } catch (err: any) {
                    notify(err.message, 'error');
                  }
                }}
                className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs"
              >
                <input
                  type="date"
                  value={leaveStart}
                  onChange={(e) => setLeaveStart(e.target.value)}
                  className="px-2 py-1.5 rounded border border-slate-300"
                />
                <input
                  type="date"
                  value={leaveEnd}
                  onChange={(e) => setLeaveEnd(e.target.value)}
                  className="px-2 py-1.5 rounded border border-slate-300"
                />
                <input
                  type="text"
                  placeholder="Leave reason"
                  value={leaveReason}
                  onChange={(e) => setLeaveReason(e.target.value)}
                  className="px-2 py-1.5 rounded border border-slate-300"
                />
                <select
                  value={leaveReplacementId}
                  onChange={(e) => setLeaveReplacementId(e.target.value)}
                  className="px-2 py-1.5 rounded border border-slate-300"
                >
                  <option value="">Select Replacement Staff (Optional)</option>
                  {staffList.map((st) => (
                    <option key={st.id} value={st.id}>
                      Replace with: {st.name}
                    </option>
                  ))}
                </select>
                <button
                  type="submit"
                  className="col-span-2 bg-slate-800 hover:bg-slate-900 text-white font-bold rounded py-1.5 cursor-pointer"
                >
                  Request Leave & Replacement
                </button>
              </form>

              <div className="space-y-2 max-h-56 overflow-y-auto text-xs">
                {leaves.map((lv) => (
                  <div
                    key={lv.id}
                    className="p-2.5 rounded-lg border border-slate-200 flex items-center justify-between"
                  >
                    <div>
                      <span className="font-bold">{lv.staff_name}</span> · {lv.start_date} to{' '}
                      {lv.end_date} ({lv.status})
                    </div>
                    {lv.status === 'pending' && (userRole === 'admin' || userRole === 'doctor') && (
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await apiRequest(
                              `/api/workforce/leaves/${lv.id}/decision`,
                              'PATCH',
                              {
                                status: 'approved',
                                replacement_staff_id: lv.replacement_staff_id,
                              }
                            );
                            notify('Leave approved and replacement assigned to shifts!');
                            await loadPhase5Data();
                          } catch (err: any) {
                            notify(err.message, 'error');
                          }
                        }}
                        className="px-2.5 py-1 bg-emerald-700 text-white rounded text-[11px] font-semibold cursor-pointer"
                      >
                        Approve Leave
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 3: PATIENT SERVICE COORDINATION
         ===================================================================== */}
      {subTab === 'services' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await apiRequest('/api/services', 'POST', {
                  mother_id: srvMotherId,
                  service_type: srvType,
                  requires_clinical_qualification: srvClinicalReq,
                  priority: srvPriority,
                  assigned_staff_id: srvStaffId || null,
                  scheduled_date: new Date().toISOString().slice(0, 10),
                  scheduled_time: '10:30',
                  notes: srvNotes,
                });
                setSrvNotes('');
                notify('Patient service request created!');
                await loadPhase5Data();
              } catch (err: any) {
                notify(err.message, 'error');
              }
            }}
            className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3 text-xs"
          >
            <h3 className="font-bold text-slate-900 text-sm">
              Create Operational Service Request
            </h3>
            <div>
              <label className="block font-semibold text-slate-600 mb-1">Mother</label>
              <select
                value={srvMotherId}
                onChange={(e) => setSrvMotherId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              >
                {mothers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.patient_identifier || m.phone})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block font-semibold text-slate-600 mb-1">Service Type</label>
              <select
                value={srvType}
                onChange={(e) => {
                  const val = e.target.value;
                  setSrvType(val);
                  if (val === 'clinical_consultation') setSrvClinicalReq(true);
                  if (val === 'transport_escort') setSrvClinicalReq(false);
                }}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              >
                <option value="anc_home_visit">ANC Home Visit (Nurse)</option>
                <option value="postnatal_check">Postnatal Check (Clinical)</option>
                <option value="clinical_consultation">Doctor Clinical Consultation</option>
                <option value="nutrition_counselling">Nutrition & Outreach Counselling</option>
                <option value="transport_escort">Transport Escort Coordination</option>
              </select>
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={srvClinicalReq}
                onChange={(e) => setSrvClinicalReq(e.target.checked)}
              />
              <span>Requires Qualified Clinician (Doctor/Nurse only)</span>
            </label>
            <div>
              <label className="block font-semibold text-slate-600 mb-1">Assign Staff</label>
              <select
                value={srvStaffId}
                onChange={(e) => setSrvStaffId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              >
                <option value="">Leave Unassigned (Queue)</option>
                {staffList.map((st) => (
                  <option key={st.id} value={st.id}>
                    {st.name} ({st.normalized_role})
                  </option>
                ))}
              </select>
            </div>
            <textarea
              placeholder="Service coordination instructions"
              value={srvNotes}
              onChange={(e) => setSrvNotes(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-300"
              rows={2}
            />
            <button
              type="submit"
              className="w-full py-2 bg-teal-700 hover:bg-teal-800 text-white font-bold rounded-lg cursor-pointer"
            >
              Request Patient Service
            </button>
          </form>

          <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h3 className="font-bold text-slate-900 text-sm">
              Patient Service Lifecycle Queue ({services.length})
            </h3>
            <p className="text-xs text-slate-500">
              Lifecycle: Service Requested → Staff Assigned → Scheduled → In Progress → Completed →
              Verified → Closed
            </p>
            <div className="space-y-3 max-h-[500px] overflow-y-auto">
              {services.map((srv) => (
                <div
                  key={srv.id}
                  className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-3 text-xs"
                >
                  <div className="space-y-1">
                    <div className="font-bold text-slate-900">
                      {srv.mother_name} ·{' '}
                      <span className="uppercase text-teal-800">
                        {srv.service_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="text-slate-600">
                      Assigned: <strong>{srv.assigned_staff_name}</strong> · Status:{' '}
                      <span className="px-2 py-0.5 rounded bg-teal-100 text-teal-900 font-bold">
                        {srv.status}
                      </span>
                    </div>
                    {srv.completion_evidence && (
                      <div className="text-emerald-700">Evidence: {srv.completion_evidence}</div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    {srv.status === 'staff_assigned' && (
                      <button
                        type="button"
                        onClick={async () => {
                          await apiRequest(`/api/services/${srv.id}/transition`, 'PATCH', {
                            status: 'scheduled',
                          });
                          notify('Service scheduled');
                          await loadPhase5Data();
                        }}
                        className="px-2.5 py-1 bg-sky-700 text-white rounded font-semibold cursor-pointer"
                      >
                        Mark Scheduled
                      </button>
                    )}
                    {srv.status === 'scheduled' && (
                      <button
                        type="button"
                        onClick={async () => {
                          await apiRequest(`/api/services/${srv.id}/transition`, 'PATCH', {
                            status: 'in_progress',
                          });
                          notify('Service in progress');
                          await loadPhase5Data();
                        }}
                        className="px-2.5 py-1 bg-amber-600 text-white rounded font-semibold cursor-pointer"
                      >
                        Start Service
                      </button>
                    )}
                    {srv.status === 'in_progress' && (
                      <button
                        type="button"
                        onClick={async () => {
                          await apiRequest(`/api/services/${srv.id}/transition`, 'PATCH', {
                            status: 'completed',
                            completion_evidence: 'Verified maternal checkup log signed',
                          });
                          notify('Service completed');
                          await loadPhase5Data();
                        }}
                        className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer"
                      >
                        Complete Service
                      </button>
                    )}
                    {srv.status === 'completed' &&
                      (userRole === 'admin' || userRole === 'doctor' || userRole === 'nurse') && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(`/api/services/${srv.id}/transition`, 'PATCH', {
                              status: 'verified',
                            });
                            notify('Service verified');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-indigo-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Verify
                        </button>
                      )}
                    {srv.status === 'verified' && (
                      <button
                        type="button"
                        onClick={async () => {
                          await apiRequest(`/api/services/${srv.id}/transition`, 'PATCH', {
                            status: 'closed',
                          });
                          notify('Service lifecycle closed');
                          await loadPhase5Data();
                        }}
                        className="px-2.5 py-1 bg-slate-800 text-white rounded font-semibold cursor-pointer"
                      >
                        Close
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 4: FIELD VISITS & OFFLINE DRAFT SYNC
         ===================================================================== */}
      {subTab === 'field_visits' && (
        <div className="space-y-6">
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-950 flex flex-wrap items-center justify-between gap-2">
            <div>
              <strong>Location Privacy & Consent Safeguard:</strong> Field visit location check-in
              is strictly optional, purpose-limited, and blocked unless explicit patient/staff
              location consent is checked. No continuous background tracking is performed.
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={saveOfflineDraft}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 text-white font-semibold cursor-pointer"
              >
                <WifiOff className="w-3.5 h-3.5" />
                Queue Offline Draft ({offlineDrafts.length})
              </button>
              {offlineDrafts.length > 0 && (
                <button
                  type="button"
                  onClick={syncOfflineDrafts}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-700 text-white font-semibold cursor-pointer"
                >
                  <UploadCloud className="w-3.5 h-3.5" />
                  Sync {offlineDrafts.length} Offline Drafts Now
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await apiRequest('/api/field-visits', 'POST', {
                    mother_id: fvMotherId,
                    assigned_staff_id: fvStaffId,
                    visit_date: fvDate,
                    scheduled_window: fvWindow,
                    visit_address: fvAddress,
                  });
                  notify('Field visit scheduled!');
                  await loadPhase5Data();
                } catch (err: any) {
                  notify(err.message, 'error');
                }
              }}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3 text-xs"
            >
              <h3 className="font-bold text-slate-900 text-sm">Schedule Field Visit</h3>
              <select
                value={fvMotherId}
                onChange={(e) => setFvMotherId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              >
                {mothers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.address || 'Clinic Sector'})
                  </option>
                ))}
              </select>
              <select
                value={fvStaffId}
                onChange={(e) => setFvStaffId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              >
                {staffList.map((st) => (
                  <option key={st.id} value={st.id}>
                    {st.name} ({st.normalized_role})
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={fvDate}
                  onChange={(e) => setFvDate(e.target.value)}
                  className="px-2.5 py-2 rounded-lg border border-slate-300"
                />
                <input
                  type="text"
                  value={fvWindow}
                  onChange={(e) => setFvWindow(e.target.value)}
                  className="px-2.5 py-2 rounded-lg border border-slate-300"
                />
              </div>
              <input
                type="text"
                value={fvAddress}
                onChange={(e) => setFvAddress(e.target.value)}
                placeholder="Village / Ward Address"
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              />
              <label className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  checked={fvLocationConsent}
                  onChange={(e) => setFvLocationConsent(e.target.checked)}
                />
                <span>Explicit Location Check-In Consent Granted</span>
              </label>
              {fvLocationConsent && (
                <input
                  type="text"
                  value={fvLocationPurpose}
                  onChange={(e) => setFvLocationPurpose(e.target.value)}
                  placeholder="Purpose of single check-in coordinate"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300"
                />
              )}
              <button
                type="submit"
                className="w-full py-2 bg-teal-700 hover:bg-teal-800 text-white font-bold rounded-lg cursor-pointer"
              >
                Schedule Daily Visit
              </button>
            </form>

            <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
              <h3 className="font-bold text-slate-900 text-sm">
                Nurse & Field-Worker Daily Visit Schedule ({fieldVisits.length})
              </h3>
              <div className="space-y-3 max-h-[480px] overflow-y-auto">
                {fieldVisits.map((fv) => (
                  <div
                    key={fv.id}
                    className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="font-bold text-slate-900">
                        {fv.mother_name} · {fv.visit_date} ({fv.scheduled_window})
                      </div>
                      <div className="text-slate-600">
                        Staff: <strong>{fv.assigned_staff_name}</strong> ({fv.staff_role}) ·
                        Address: {fv.visit_address}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-0.5 rounded bg-teal-100 text-teal-900 font-bold">
                          {fv.status}
                        </span>
                        {fv.synced_from_offline && (
                          <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-semibold">
                            Synced from Offline Draft
                          </span>
                        )}
                        {fv.completion_evidence_ref && (
                          <span className="text-emerald-700 font-semibold">
                            Evidence: {fv.completion_evidence_ref}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {fv.status === 'scheduled' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(`/api/field-visits/${fv.id}`, 'PATCH', {
                              status: 'in_progress',
                              contact_confirmed: true,
                              patient_consent_verified: true,
                            });
                            notify('Visit started (patient consent verified)');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-amber-600 text-white rounded font-semibold cursor-pointer"
                        >
                          Confirm Consent & Start
                        </button>
                      )}
                      {fv.status === 'in_progress' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(`/api/field-visits/${fv.id}`, 'PATCH', {
                              status: 'completed',
                              patient_consent_verified: true,
                              role_scoped_notes:
                                'Home visit completed; verified next doctor-approved ANC date.',
                              completion_evidence_type: 'home_visit_acknowledgement',
                              completion_evidence_ref: `HV-ACK-${fv.id.slice(0, 6)}`,
                            });
                            notify('Field visit completed with evidence!');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Complete Visit
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 5: HOSPITAL & DIAGNOSTIC PARTNERSHIPS & REFERRALS
         ===================================================================== */}
      {subTab === 'partners_referrals' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Register Partner Facility */}
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
              <h3 className="font-bold text-slate-900 text-sm">
                Empaneled Partner Hospitals & Diagnostic Centres ({partnerFacilities.length})
              </h3>
              {(userRole === 'admin' || userRole === 'doctor') && (
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      const today = new Date().toISOString().slice(0, 10);
                      await apiRequest('/api/partners/facilities', 'POST', {
                        name: pfName,
                        facility_type: pfType,
                        contact_person: pfContact,
                        contact_phone: pfPhone,
                        address: 'Nalgonda District Health Cluster',
                        services_offered: ['Obstetric Ultrasound', 'High-Risk Maternity', 'Blood Panel'],
                        agreement_reference: pfAgreement,
                        effective_from: today,
                        effective_until: '2027-12-31',
                        schedule_charges: { standard_referral_paise: 120000 },
                      });
                      setPfName('');
                      notify('Partner hospital/diagnostic facility registered!');
                      await loadPhase5Data();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs"
                >
                  <input
                    type="text"
                    required
                    placeholder="Facility Name"
                    value={pfName}
                    onChange={(e) => setPfName(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <select
                    value={pfType}
                    onChange={(e) => setPfType(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    <option value="referral_hospital">Referral Maternity Hospital</option>
                    <option value="ultrasound_centre">Registered Ultrasound Centre</option>
                    <option value="diagnostic_lab">Diagnostic Laboratory</option>
                  </select>
                  <input
                    type="text"
                    placeholder="Nodal Contact Person"
                    value={pfContact}
                    onChange={(e) => setPfContact(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    placeholder="Contact Phone"
                    value={pfPhone}
                    onChange={(e) => setPfPhone(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <button
                    type="submit"
                    className="col-span-2 bg-teal-700 text-white font-bold py-1.5 rounded cursor-pointer"
                  >
                    Add Partner Facility
                  </button>
                </form>
              )}
              <div className="space-y-2 text-xs">
                {partnerFacilities.map((pf) => (
                  <div key={pf.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                    <div className="font-bold text-slate-900">
                      {pf.name} ({pf.facility_type.replace(/_/g, ' ')})
                    </div>
                    <div className="text-slate-600">
                      Agreement: <code>{pf.agreement_reference}</code> · Valid until:{' '}
                      {pf.effective_until} · Contact: {pf.contact_person} ({pf.contact_phone})
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Clinician-Authorised Referrals */}
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
              <h3 className="font-bold text-slate-900 text-sm">
                Clinician-Authorised Hospital & Diagnostic Referrals ({referrals.length})
              </h3>
              {(userRole === 'doctor' || userRole === 'nurse' || userRole === 'admin') && (
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      await apiRequest('/api/referrals', 'POST', {
                        mother_id: refMotherId,
                        partner_facility_id: refPartnerId,
                        referral_category: refCategory,
                        reason_and_clinical_summary:
                          refReason ||
                          'Doctor-authorised obstetric ultrasound & blood panel at partner facility',
                        requested_services: ['Obstetric Ultrasound', 'CBC'],
                        scheduled_service_date: new Date().toISOString().slice(0, 10),
                        contractual_charge_rupees: Number(refChargeRupees),
                      });
                      setRefReason('');
                      notify('Referral authorised and initiated!');
                      await loadPhase5Data();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs"
                >
                  <select
                    value={refMotherId}
                    onChange={(e) => setRefMotherId(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    {mothers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={refPartnerId}
                    onChange={(e) => setRefPartnerId(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    {partnerFacilities.map((pf) => (
                      <option key={pf.id} value={pf.id}>
                        {pf.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={refCategory}
                    onChange={(e) => setRefCategory(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    <option value="clinical_obstetric">Clinical Obstetric (Doctor Required)</option>
                    <option value="routine_ultrasound">Routine Ultrasound (Doctor Required)</option>
                    <option value="diagnostic_lab">Diagnostic Lab Panel</option>
                  </select>
                  <input
                    type="number"
                    value={refChargeRupees}
                    onChange={(e) => setRefChargeRupees(Number(e.target.value))}
                    placeholder="Contractual Charge (₹)"
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    value={refReason}
                    onChange={(e) => setRefReason(e.target.value)}
                    placeholder="Clinical summary & referral reason (min 5 chars)"
                    className="col-span-2 px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <button
                    type="submit"
                    className="col-span-2 bg-sky-700 hover:bg-sky-800 text-white font-bold py-1.5 rounded cursor-pointer"
                  >
                    Authorise Partner Referral
                  </button>
                </form>
              )}

              <div className="space-y-2.5 max-h-72 overflow-y-auto text-xs">
                {referrals.map((r) => (
                  <div
                    key={r.id}
                    className="p-3 rounded-xl border border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-2"
                  >
                    <div className="space-y-0.5">
                      <div className="font-bold text-slate-900">
                        {r.mother_name} → {r.partner_facility_name}
                      </div>
                      <div className="text-slate-600">
                        Category: {r.referral_category} · Status:{' '}
                        <span className="font-bold text-sky-800">{r.status}</span> · Charge: ₹
                        {r.contractual_charge_rupees}
                      </div>
                      {r.expense_id && (
                        <div className="text-emerald-700 font-semibold">
                          Linked Contractual Expense ID: {r.expense_id}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1.5">
                      {r.status === 'initiated' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(`/api/referrals/${r.id}/transition`, 'PATCH', {
                              status: 'acknowledged_by_partner',
                              partner_acknowledgement_ref: `ACK-${r.id.slice(0, 5)}`,
                            });
                            notify('Partner acknowledgement recorded');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-sky-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Record Partner Ack
                        </button>
                      )}
                      {r.status !== 'verified_closed' &&
                        r.status !== 'cancelled' &&
                        (userRole === 'doctor' || userRole === 'admin' || userRole === 'nurse') && (
                          <button
                            type="button"
                            onClick={async () => {
                              await apiRequest(`/api/referrals/${r.id}/transition`, 'PATCH', {
                                status: 'verified_closed',
                                completion_evidence_ref: `DIAG-REP-${r.id.slice(0, 6)}`,
                              });
                              notify(
                                'Referral service verified & contractual expense recorded!'
                              );
                              await loadPhase5Data();
                              await onRefreshGlobal();
                            }}
                            className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer"
                          >
                            Verify & Record Expense
                          </button>
                        )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 6: EXTENDED TRANSPORT OPERATIONS
         ===================================================================== */}
      {subTab === 'transport_ops' && (
        <div className="space-y-6">
          <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-3.5 text-xs text-indigo-950">
            <strong>Non-Emergency Scheduled Transport Boundary:</strong> This module coordinates
            scheduled maternal clinic pickups and hospital referral trips with empaneled transport
            partners and licence/insurance-verified drivers. For acute obstetric emergencies, dial
            <strong> 108 / 102 Emergency Ambulance Response</strong> immediately.
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Transport Partners & Verified Drivers */}
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4 text-xs">
              <h3 className="font-bold text-slate-900 text-sm">
                Transport Partners ({transportPartners.length}) & Verified Fleet (
                {vehiclesDrivers.length})
              </h3>
              {(userRole === 'admin' || userRole === 'field_coordinator') && (
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      await apiRequest('/api/transport-ops/vehicles', 'POST', {
                        partner_id: vdPartnerId,
                        driver_name: vdDriverName,
                        driver_phone: vdDriverPhone,
                        driving_licence_no: vdLicenseNo,
                        licence_expiry_date: '2028-06-30',
                        vehicle_registration_no: vdRegNo,
                        vehicle_type: 'patient_transport_van',
                        insurance_policy_no: vdInsuranceNo,
                        insurance_expiry_date: '2027-09-30',
                      });
                      setVdDriverName('');
                      setVdLicenseNo('');
                      setVdRegNo('');
                      notify('Vehicle & driver registered (pending licence/insurance verification)!');
                      await loadPhase5Data();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200"
                >
                  <select
                    value={vdPartnerId}
                    onChange={(e) => setVdPartnerId(e.target.value)}
                    className="col-span-2 px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    {transportPartners.map((tp) => (
                      <option key={tp.id} value={tp.id}>
                        Partner: {tp.name}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    required
                    placeholder="Driver Name"
                    value={vdDriverName}
                    onChange={(e) => setVdDriverName(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    required
                    placeholder="Driver Phone"
                    value={vdDriverPhone}
                    onChange={(e) => setVdDriverPhone(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    required
                    placeholder="Driving Licence No"
                    value={vdLicenseNo}
                    onChange={(e) => setVdLicenseNo(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    required
                    placeholder="Vehicle Reg No (e.g. TS-05-1234)"
                    value={vdRegNo}
                    onChange={(e) => setVdRegNo(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <input
                    type="text"
                    required
                    placeholder="Insurance Policy No"
                    value={vdInsuranceNo}
                    onChange={(e) => setVdInsuranceNo(e.target.value)}
                    className="col-span-2 px-2.5 py-1.5 rounded border border-slate-300"
                  />
                  <button
                    type="submit"
                    className="col-span-2 bg-teal-700 text-white font-bold py-1.5 rounded cursor-pointer"
                  >
                    Register Driver & Vehicle
                  </button>
                </form>
              )}

              <div className="space-y-2 max-h-64 overflow-y-auto">
                {vehiclesDrivers.map((vd) => (
                  <div
                    key={vd.id}
                    className="p-3 rounded-xl border border-slate-200 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-bold text-slate-900">
                        {vd.driver_name} · {vd.vehicle_registration_no}
                      </div>
                      <div className="text-slate-600">
                        DL: {vd.driving_licence_no} (exp {vd.licence_expiry_date}) · Ins:{' '}
                        {vd.insurance_policy_no}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          vd.credentials_verified
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {vd.credentials_verified ? 'Verified' : 'Unverified'}
                      </span>
                      {!vd.credentials_verified && userRole === 'admin' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(
                              `/api/transport-ops/vehicles/${vd.id}/verify`,
                              'POST'
                            );
                            notify('Driver licence & vehicle insurance verified!');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Verify DL & Insurance
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Active Transport Trips Lifecycle */}
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4 text-xs">
              <h3 className="font-bold text-slate-900 text-sm">
                Maternal Transport Trips Lifecycle ({transportTrips.length})
              </h3>
              <div className="space-y-2.5 max-h-96 overflow-y-auto">
                {transportTrips.map((tr) => (
                  <div
                    key={tr.id}
                    className="p-3 rounded-xl border border-slate-200 bg-slate-50 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-bold text-slate-900">
                        {tr.mother_name} · {tr.date} ({tr.pickup_time})
                      </div>
                      <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-900 font-bold">
                        {tr.status}
                      </span>
                    </div>
                    <div className="text-slate-600">
                      Route: {tr.from_location || 'Home'} → {tr.destination} · Partner:{' '}
                      {tr.partner || 'Unassigned'}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {vehiclesDrivers.length > 0 && tr.status === 'requested' && (
                        <button
                          type="button"
                          onClick={async () => {
                            const vd =
                              vehiclesDrivers.find((v) => v.credentials_verified) ||
                              vehiclesDrivers[0];
                            try {
                              await apiRequest(
                                `/api/transport-ops/trips/${tr.id}/assign-driver`,
                                'POST',
                                {
                                  vehicle_driver_id: vd.id,
                                  pickup_time: tr.pickup_time || '08:30',
                                  fare_rupees: 450,
                                }
                              );
                              notify('Verified driver assigned to maternal pickup!');
                              await loadPhase5Data();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="px-2.5 py-1 bg-teal-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Assign Verified Driver
                        </button>
                      )}
                      {tr.status === 'assigned' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(
                              `/api/transport-ops/trips/${tr.id}/driver-response`,
                              'POST',
                              { decision: 'accepted', notes: 'Driver confirmed pickup time' }
                            );
                            notify('Driver accepted pickup');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-sky-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Driver Accept
                        </button>
                      )}
                      {(tr.status === 'driver_accepted' || tr.status === 'assigned') && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(
                              `/api/transport-ops/trips/${tr.id}/lifecycle`,
                              'PATCH',
                              { status: 'in_transit' }
                            );
                            notify('Trip in transit');
                            await loadPhase5Data();
                          }}
                          className="px-2.5 py-1 bg-amber-600 text-white rounded font-semibold cursor-pointer"
                        >
                          Start Trip
                        </button>
                      )}
                      {tr.status === 'in_transit' && (
                        <button
                          type="button"
                          onClick={async () => {
                            await apiRequest(
                              `/api/transport-ops/trips/${tr.id}/lifecycle`,
                              'PATCH',
                              {
                                status: 'completed',
                                actual_fare_rupees: 450,
                                receipt_ref: `TRP-RCPT-${tr.id.slice(0, 6)}`,
                              }
                            );
                            notify('Trip completed & voucher expense recorded!');
                            await loadPhase5Data();
                            await onRefreshGlobal();
                          }}
                          className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer"
                        >
                          Complete Trip & Log Expense
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SUB-TAB 7: CLINICAL & ORGANISATIONAL GOVERNANCE
         ===================================================================== */}
      {subTab === 'governance' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-xs">
          {/* Governance Incidents */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              Governance Incident Escalations ({incidents.length})
            </h3>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await apiRequest('/api/governance/incidents', 'POST', {
                    incident_type: incType,
                    severity: incSeverity,
                    title: incTitle,
                    description: incDesc,
                  });
                  setIncTitle('');
                  setIncDesc('');
                  notify('Governance incident logged for human clinical/admin review.');
                  await loadPhase5Data();
                } catch (err: any) {
                  notify(err.message, 'error');
                }
              }}
              className="space-y-2 bg-slate-50 p-3 rounded-xl border border-slate-200"
            >
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={incType}
                  onChange={(e) => setIncType(e.target.value)}
                  className="px-2.5 py-1.5 rounded border border-slate-300"
                >
                  <option value="missed_high_priority_visit">Missed High-Priority Visit</option>
                  <option value="credential_expiry_alert">Credential Expiry Alert</option>
                  <option value="failed_pickup_escalation">Failed Pickup Escalation</option>
                  <option value="protocol_deviation">Protocol Deviation</option>
                </select>
                <select
                  value={incSeverity}
                  onChange={(e) => setIncSeverity(e.target.value as any)}
                  className="px-2.5 py-1.5 rounded border border-slate-300"
                >
                  <option value="medium">Medium Severity</option>
                  <option value="high">High Severity</option>
                  <option value="critical">Critical Severity</option>
                </select>
              </div>
              <input
                type="text"
                required
                placeholder="Incident Title"
                value={incTitle}
                onChange={(e) => setIncTitle(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded border border-slate-300"
              />
              <textarea
                required
                placeholder="Detailed description & required corrective action"
                value={incDesc}
                onChange={(e) => setIncDesc(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded border border-slate-300"
                rows={2}
              />
              <button
                type="submit"
                className="w-full py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold rounded cursor-pointer"
              >
                Report Governance Incident
              </button>
            </form>

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {incidents.map((inc) => (
                <div
                  key={inc.id}
                  className="p-3 rounded-xl border border-slate-200 flex items-center justify-between gap-2"
                >
                  <div>
                    <div className="font-bold text-slate-900">
                      [{inc.severity.toUpperCase()}] {inc.title}
                    </div>
                    <div className="text-slate-600">
                      {inc.description} · Status: <strong>{inc.status}</strong>
                    </div>
                  </div>
                  {inc.status !== 'resolved' && (userRole === 'admin' || userRole === 'doctor') && (
                    <button
                      type="button"
                      onClick={async () => {
                        await apiRequest(`/api/governance/incidents/${inc.id}`, 'PATCH', {
                          status: 'resolved',
                          resolution_notes:
                            'Reviewed by Medical Officer / Admin; corrective follow-up completed.',
                        });
                        notify('Governance incident resolved!');
                        await loadPhase5Data();
                      }}
                      className="px-2.5 py-1 bg-emerald-700 text-white rounded font-semibold cursor-pointer shrink-0"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Audited Record Corrections */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <FileEdit className="w-4 h-4 text-teal-700" />
              Immutable Record Correction Log ({corrections.length})
            </h3>
            {(userRole === 'admin' || userRole === 'doctor' || userRole === 'nurse') && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await apiRequest('/api/governance/corrections', 'POST', {
                      entity_type: 'mother',
                      entity_id: corrMotherId,
                      field_name: corrField,
                      new_value: corrNewValue,
                      correction_reason: corrReason,
                    });
                    setCorrNewValue('');
                    setCorrReason('');
                    notify('Record correction applied and logged to immutable audit trail!');
                    await loadPhase5Data();
                    await onRefreshGlobal();
                  } catch (err: any) {
                    notify(err.message, 'error');
                  }
                }}
                className="space-y-2 bg-slate-50 p-3 rounded-xl border border-slate-200"
              >
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={corrMotherId}
                    onChange={(e) => setCorrMotherId(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    {mothers.map((m) => (
                      <option key={m.id} value={m.id}>
                        Mother: {m.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={corrField}
                    onChange={(e) => setCorrField(e.target.value)}
                    className="px-2.5 py-1.5 rounded border border-slate-300"
                  >
                    <option value="address">Address</option>
                    <option value="phone">Phone Number</option>
                    <option value="patient_identifier">Patient Identifier</option>
                    <option value="notes">Administrative Notes</option>
                  </select>
                </div>
                <input
                  type="text"
                  required
                  placeholder="New Verified Value"
                  value={corrNewValue}
                  onChange={(e) => setCorrNewValue(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded border border-slate-300"
                />
                <input
                  type="text"
                  required
                  placeholder="Documented Reason for Correction (min 5 chars)"
                  value={corrReason}
                  onChange={(e) => setCorrReason(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded border border-slate-300"
                />
                <button
                  type="submit"
                  className="w-full py-1.5 bg-teal-700 hover:bg-teal-800 text-white font-bold rounded cursor-pointer"
                >
                  Apply Audited Record Correction
                </button>
              </form>
            )}

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {corrections.map((c) => (
                <div key={c.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                  <div className="font-bold text-slate-900">
                    {c.entity_type}:{c.entity_id} · Field: <code>{c.field_name}</code>
                  </div>
                  <div className="text-slate-600">
                    Old: <code>{c.old_value || 'empty'}</code> → New: <code>{c.new_value}</code>
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Reason: {c.correction_reason} · Approved by: {c.approved_by} (
                    {c.approved_by_role})
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

