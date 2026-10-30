import React, { useState, useEffect, useCallback } from 'react';
import {
  IndianRupee,
  FileCheck2,
  Building2,
  Landmark,
  Receipt,
  Truck,
  ShieldCheck,
  AlertTriangle,
  Download,
  PlayCircle,
  CheckCircle2,
  RefreshCw,
  FileSpreadsheet,
  Lock,
  History,
  Layers,
} from 'lucide-react';
import { apiRequest, getStoredToken } from '../api';
import type { StaffMember } from '../types';

interface Props {
  currentUser: StaffMember;
  staffList: StaffMember[];
  notify: (text: string, type?: 'success' | 'error') => void;
  onRefreshGlobal: () => Promise<void>;
}

type SubTab =
  | 'overview'
  | 'contracts'
  | 'budgets'
  | 'payroll'
  | 'claims'
  | 'evidence'
  | 'reports'
  | 'audit';

export default function FinancialAccountabilityHub({
  currentUser,
  staffList,
  notify,
  onRefreshGlobal,
}: Props) {
  const userRole =
    currentUser.role === 'asha' ? 'field_coordinator' : currentUser.role;
  const isAdmin = userRole === 'admin';
  const isAdminOrDoc = userRole === 'admin' || userRole === 'doctor';

  const [subTab, setSubTab] = useState<SubTab>('overview');
  const [loading, setLoading] = useState(false);

  // Filters
  const [filterContractId, setFilterContractId] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterFacility, setFilterFacility] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  // Data States
  const [dashboard, setDashboard] = useState<any>(null);
  const [funders, setFunders] = useState<any[]>([]);
  const [contracts, setContracts] = useState<any[]>([]);
  const [budgets, setBudgets] = useState<any[]>([]);
  const [statutoryConfigs, setStatutoryConfigs] = useState<any[]>([]);
  const [agreements, setAgreements] = useState<any[]>([]);
  const [payrollRuns, setPayrollRuns] = useState<any[]>([]);
  const [payslips, setPayslips] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [claims, setClaims] = useState<any[]>([]);
  const [fundingClaims, setFundingClaims] = useState<any[]>([]);
  const [selectedEvidencePkg, setSelectedEvidencePkg] = useState<any>(null);
  const [reportType, setReportType] = useState('contract_funding_summary');
  const [reportData, setReportData] = useState<any>(null);
  const [auditLedger, setAuditLedger] = useState<any[]>([]);
  const [corrections, setCorrections] = useState<any[]>([]);
  const [walkthroughResult, setWalkthroughResult] = useState<any>(null);

  // Forms
  const [newContractName, setNewContractName] = useState('');
  const [newContractRef, setNewContractRef] = useState('');
  const [newContractCeilingRupees, setNewContractCeilingRupees] = useState('1500000');

  const [amendBudgetId, setAmendBudgetId] = useState('');
  const [amendCategory, setAmendCategory] = useState('transport');
  const [amendNewRupees, setAmendNewRupees] = useState('400000');
  const [amendReason, setAmendReason] = useState('');
  const [amendRef, setAmendRef] = useState('');

  const [payrollPeriod, setPayrollPeriod] = useState('2026-10');

  const [claimCategory, setClaimCategory] = useState('travel');
  const [claimMode, setClaimMode] = useState('staff_two_wheeler_mileage');
  const [claimDistanceKm, setClaimDistanceKm] = useState('25');
  const [claimAmountPaise, setClaimAmountPaise] = useState('30000');
  const [claimReceiptNo, setClaimReceiptNo] = useState('');
  const [claimDesc, setClaimDesc] = useState('');

  const [corrEntityType, setCorrEntityType] = useState<'expense_claim' | 'payslip_record' | 'expense'>('expense_claim');
  const [corrEntityId, setCorrEntityId] = useState('');
  const [corrField, setCorrField] = useState<'amount_paise' | 'allowance_paise' | 'description' | 'correction_note'>('amount_paise');
  const [corrNewPaise, setCorrNewPaise] = useState('35000');
  const [corrReason, setCorrReason] = useState('');

  const loadFinanceData = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterContractId) qs.set('contract_id', filterContractId);
      if (filterStatus) qs.set('status', filterStatus);
      if (filterFacility) qs.set('facility', filterFacility);
      if (filterDateFrom) qs.set('date_from', filterDateFrom);
      if (filterDateTo) qs.set('date_to', filterDateTo);

      const dashRes = await apiRequest<any>(`/api/finance/dashboard?${qs.toString()}`);
      setDashboard(dashRes);
      setContracts(dashRes.contracts || []);
      setBudgets(dashRes.budgets || []);
      setClaims(dashRes.expense_claims || []);

      const [polRes, slipRes, agRes] = await Promise.all([
        apiRequest<any[]>('/api/finance/policies'),
        apiRequest<any[]>('/api/finance/payroll/payslips'),
        apiRequest<any[]>('/api/finance/payroll/agreements'),
      ]);
      setPolicies(polRes || []);
      setPayslips(slipRes || []);
      setAgreements(agRes || []);

      if (userRole !== 'field_coordinator') {
        const [fndRes, fcRes] = await Promise.all([
          apiRequest<any[]>('/api/finance/funders'),
          apiRequest<any[]>('/api/finance/funding-claims'),
        ]);
        setFunders(fndRes || []);
        setFundingClaims(fcRes || []);
      }

      if (isAdmin) {
        const runsRes = await apiRequest<any[]>('/api/finance/payroll/runs');
        setPayrollRuns(runsRes || []);
      }

      if (isAdminOrDoc) {
        const [statRes, ledRes, corRes, repRes] = await Promise.all([
          apiRequest<any[]>('/api/finance/payroll/statutory-configs'),
          apiRequest<any[]>('/api/finance/audit-ledger?limit=80'),
          apiRequest<any[]>('/api/finance/corrections'),
          apiRequest<any>(`/api/finance/reports/${reportType}`),
        ]);
        setStatutoryConfigs(statRes || []);
        setAuditLedger(ledRes || []);
        setCorrections(corRes || []);
        setReportData(repRes);
      }
    } catch (err: any) {
      notify(err.message || 'Failed to load financial accountability data', 'error');
    } finally {
      setLoading(false);
    }
  }, [
    filterContractId,
    filterStatus,
    filterFacility,
    filterDateFrom,
    filterDateTo,
    userRole,
    isAdmin,
    isAdminOrDoc,
    reportType,
    notify,
  ]);

  useEffect(() => {
    loadFinanceData();
  }, [loadFinanceData]);

  const handleRunWalkthrough = async () => {
    try {
      setLoading(true);
      const res = await apiRequest<any>('/api/finance/demo-walkthrough', 'POST', {});
      setWalkthroughResult(res);
      setSelectedEvidencePkg(res.supporting_evidence_package);
      notify('Completed 12-Step Funded Maternal Programme Scenario!');
      await loadFinanceData();
      await onRefreshGlobal();
    } catch (err: any) {
      notify(err.message || 'Walkthrough failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadExport = async (type: string, fmt: 'csv' | 'pdf') => {
    try {
      const token = getStoredToken();
      const resp = await fetch(`/api/finance/reports/${type}/export?format=${fmt}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        throw new Error(`Export failed (${resp.status})`);
      }
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${type}_${currentUser.clinic}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      notify(`Downloaded ${type.toUpperCase()} (${fmt.toUpperCase()})`);
    } catch (err: any) {
      notify(err.message || 'Export download failed', 'error');
    }
  };

  const handleCreateDraftContract = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!funders.length) {
      notify('Create or seed a funding organisation first', 'error');
      return;
    }
    try {
      const ceilingPaise = parseInt(newContractCeilingRupees, 10) * 100;
      await apiRequest('/api/finance/contracts', 'POST', {
        funder_id: funders[0].id,
        programme_name: newContractName,
        contract_reference: newContractRef,
        effective_from: '2026-04-01',
        effective_until: '2027-03-31',
        funding_ceiling_paise: ceilingPaise,
        funder_share_bps: 9000,
        reimbursement_basis: 'actual_verified_cost',
        allow_private_transport_reimbursement: false,
        objectives: ['4+ ANC Visits', 'Safe Rural Maternal Transport'],
        delivery_obligations: ['Monthly Service-to-Funding Evidence Package'],
      });
      setNewContractName('');
      setNewContractRef('');
      notify('Created new Draft Programme Contract (marked as unapproved proposal)');
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleTransitionContract = async (cid: string, targetState: string) => {
    try {
      await apiRequest(`/api/finance/contracts/${cid}/state`, 'POST', {
        target_state: targetState,
        sanction_order_ref:
          targetState === 'approved' ? `SYN-SANCTION-${Date.now()}` : '',
        approval_evidence_ref:
          targetState === 'approved' ? `SIMULATED-APPROVAL-${Date.now()}` : '',
        is_simulated_approval: true,
        notes: `State transition to ${targetState}`,
      });
      notify(`Contract transitioned to '${targetState}'`);
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleAmendBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetBid = amendBudgetId || (budgets[0] && budgets[0].id);
    if (!targetBid) return;
    try {
      const newPaise = parseInt(amendNewRupees, 10) * 100;
      await apiRequest(`/api/finance/budgets/${targetBid}/amendments`, 'POST', {
        category: amendCategory,
        new_allocated_paise: newPaise,
        reason: amendReason,
        approval_reference: amendRef,
      });
      setAmendReason('');
      setAmendRef('');
      notify(`Amended '${amendCategory}' budget allocation with version history`);
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleCalculatePayroll = async () => {
    try {
      await apiRequest('/api/finance/payroll/runs', 'POST', {
        period_month: payrollPeriod,
        contract_id: contracts[0]?.id,
        budget_id: budgets[0]?.id,
      });
      notify(`Calculated payroll batch for ${payrollPeriod}`);
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handlePayrollTransition = async (rid: string, nextStatus: string) => {
    try {
      await apiRequest(`/api/finance/payroll/runs/${rid}/transition`, 'POST', {
        target_status: nextStatus,
        payment_batch_ref:
          nextStatus === 'locked' || nextStatus === 'paid_verified'
            ? `BATCH-${payrollPeriod}-01`
            : '',
        payment_evidence_ref:
          nextStatus === 'paid_verified' ? `UTR-VERIFIED-${Date.now()}` : '',
        notes: `Transitioned to ${nextStatus}`,
      });
      notify(`Payroll run transitioned to '${nextStatus}'`);
      await loadFinanceData();
      await onRefreshGlobal();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleSubmitClaim = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiRequest('/api/finance/claims', 'POST', {
        contract_id: contracts[0]?.id,
        budget_id: budgets[0]?.id,
        policy_rule_id: policies[0]?.id,
        claim_type:
          claimCategory === 'transport'
            ? 'transport_partner_invoice'
            : 'staff_travel_claim',
        expense_category: claimCategory,
        transport_mode: claimMode,
        distance_km: parseInt(claimDistanceKm || '0', 10),
        amount_paise: parseInt(claimAmountPaise || '0', 10),
        receipt_number: claimReceiptNo,
        receipt_filename: `${claimReceiptNo}.pdf`,
        description: claimDesc,
      });
      setClaimReceiptNo('');
      setClaimDesc('');
      notify('Submitted expense reimbursement claim');
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleClaimDecision = async (cid: string, decision: string) => {
    try {
      await apiRequest(`/api/finance/claims/${cid}/decision`, 'POST', {
        decision,
        receipt_verified: true,
        reimbursement_payment_ref:
          decision === 'reimbursed_paid' ? `UTR-CLM-${Date.now()}` : '',
        notes: `Decision: ${decision}`,
      });
      notify(`Claim updated to '${decision}'`);
      await loadFinanceData();
      await onRefreshGlobal();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleInspectEvidencePackage = async (fcid: string) => {
    try {
      const pkg = await apiRequest<any>(
        `/api/finance/funding-claims/${fcid}/evidence-package`
      );
      setSelectedEvidencePkg(pkg);
      notify(`Loaded privacy-safe Supporting Evidence Package`);
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const handleSubmitCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiRequest('/api/finance/corrections', 'POST', {
        entity_type: corrEntityType,
        entity_id: corrEntityId,
        field_name: corrField,
        new_value_paise:
          corrField === 'amount_paise' || corrField === 'allowance_paise'
            ? parseInt(corrNewPaise, 10)
            : undefined,
        new_text:
          corrField === 'description' || corrField === 'correction_note'
            ? corrReason
            : '',
        reason: corrReason,
      });
      setCorrEntityId('');
      setCorrReason('');
      notify('Recorded versioned financial correction in immutable ledger');
      await loadFinanceData();
    } catch (err: any) {
      notify(err.message, 'error');
    }
  };

  const kpis = dashboard?.summary_kpis || {};
  const costAnalytics = dashboard?.cost_per_service_analytics || {};

  return (
    <div className="space-y-6">
      {/* Governance & Exact Paise Banner */}
      <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-md border border-slate-700 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Landmark className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold">
              Phase 6: Government Contracts, Programme Budgets, Payroll & Funding Accountability
            </h2>
          </div>
          <p className="text-xs text-slate-300">
            Exact Integer Paise &amp; Decimal Arithmetic · Anti-Self-Approval Enforced · Draft
            Proposals Never Shown as Approved Government Funding · Privacy-Safe Evidence Packages
          </p>
        </div>

        {isAdminOrDoc && (
          <button
            type="button"
            onClick={handleRunWalkthrough}
            disabled={loading}
            className="flex items-center gap-2 bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-xl shadow transition cursor-pointer"
          >
            <PlayCircle className="w-4 h-4" />
            Run 12-Step Funded Programme Walkthrough
          </button>
        )}
      </div>

      {/* Walkthrough Result Banner */}
      {walkthroughResult && (
        <div className="bg-emerald-50 border border-emerald-300 rounded-2xl p-4 text-xs text-emerald-950 space-y-2">
          <div className="font-bold text-sm flex items-center gap-2 text-emerald-900">
            <CheckCircle2 className="w-4 h-4 text-emerald-700" />
            12-Step End-to-End Funded Maternal Programme Scenario Completed!
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
            {(walkthroughResult.steps_completed || []).map((st: string, idx: number) => (
              <div key={idx} className="flex items-start gap-1.5">
                <span className="text-emerald-700 font-bold">✓</span>
                <span>{st}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Global Filter Bar */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-wrap items-end gap-3 text-xs">
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Programme / Contract</label>
          <select
            value={filterContractId}
            onChange={(e) => setFilterContractId(e.target.value)}
            className="border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
          >
            <option value="">All Contracts</option>
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.contract_reference} — {c.programme_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Contract Status</label>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
          >
            <option value="">All States</option>
            <option value="draft">Draft (Unapproved)</option>
            <option value="submitted">Submitted</option>
            <option value="approved">Approved</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="completed">Completed</option>
          </select>
        </div>
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Facility Scope</label>
          <input
            type="text"
            placeholder="e.g. PHC Nalgonda"
            value={filterFacility}
            onChange={(e) => setFilterFacility(e.target.value)}
            className="border border-slate-300 rounded-lg px-2.5 py-1.5 w-36"
          />
        </div>
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Date From</label>
          <input
            type="date"
            value={filterDateFrom}
            onChange={(e) => setFilterDateFrom(e.target.value)}
            className="border border-slate-300 rounded-lg px-2.5 py-1.5"
          />
        </div>
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Date To</label>
          <input
            type="date"
            value={filterDateTo}
            onChange={(e) => setFilterDateTo(e.target.value)}
            className="border border-slate-300 rounded-lg px-2.5 py-1.5"
          />
        </div>
        <button
          type="button"
          onClick={() => loadFinanceData()}
          className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Apply Filters
        </button>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {[
          { id: 'overview', label: 'Financial Overview & Cost Analytics', icon: <Layers className="w-4 h-4" /> },
          { id: 'contracts', label: 'Funding Contracts & Milestones', icon: <Landmark className="w-4 h-4" /> },
          { id: 'budgets', label: 'Programme Budgets & Cash-Flow', icon: <IndianRupee className="w-4 h-4" /> },
          { id: 'payroll', label: 'Workforce Payroll & Payslips', icon: <Building2 className="w-4 h-4" /> },
          { id: 'claims', label: 'Expense Claims & Transport Reconciliation', icon: <Truck className="w-4 h-4" /> },
          { id: 'evidence', label: 'Service-to-Funding Evidence', icon: <FileCheck2 className="w-4 h-4" /> },
          ...(isAdminOrDoc
            ? [
                { id: 'reports', label: 'Reports & CSV/PDF Exports', icon: <FileSpreadsheet className="w-4 h-4" /> },
                { id: 'audit', label: 'Audit Ledger & Corrections', icon: <History className="w-4 h-4" /> },
              ]
            : []),
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSubTab(t.id as SubTab)}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
              subTab === t.id
                ? 'bg-teal-700 text-white shadow-sm'
                : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* ===================================================================
          SUBTAB 1: OVERVIEW & COST-PER-SERVICE ANALYTICS
         =================================================================== */}
      {subTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500 font-medium">Approved Funding Ceiling</div>
              <div className="text-xl font-bold text-slate-900 mt-1">
                ₹{kpis.approved_funding_ceiling_inr || '0.00'}
              </div>
              <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                {kpis.approved_funding_ceiling_paise || 0} paise
              </div>
            </div>
            <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500 font-medium">
                Funding Received vs Outstanding
              </div>
              <div className="text-xl font-bold text-emerald-700 mt-1">
                ₹{kpis.funding_received_inr || '0.00'}
              </div>
              <div className="text-[11px] text-amber-700 mt-0.5">
                Receivable: ₹{kpis.receivables_outstanding_inr || '0.00'}
              </div>
            </div>
            <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500 font-medium">
                Approved Expenditure ({kpis.funding_utilisation_pct || '0.00%'})
              </div>
              <div className="text-xl font-bold text-sky-800 mt-1">
                ₹{kpis.expenditure_approved_inr || '0.00'}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                of ₹{kpis.budget_allocated_inr || '0.00'} allocated
              </div>
            </div>
            <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500 font-medium">Settled Funder Reimbursements</div>
              <div className="text-xl font-bold text-purple-800 mt-1">
                ₹{kpis.expenditure_reimbursed_inr || '0.00'}
              </div>
              <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                {kpis.expenditure_reimbursed_paise || 0} paise
              </div>
            </div>
          </div>

          {/* Cost-Per-Service Analytics */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-3">
              Cost-per-Service &amp; Operational Efficiency Analytics (Exact Decimal Paise)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-slate-500">Avg. Cost per Maternal Service Unit</div>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  ₹{costAnalytics.avg_cost_per_service_unit_inr || '0.00'}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  Services: {costAnalytics.completed_services_count || 0} · Field Visits:{' '}
                  {costAnalytics.completed_field_visits_count || 0} · Trips:{' '}
                  {costAnalytics.completed_transport_trips_count || 0}
                </div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-slate-500">Avg. Cost per Completed Transport Trip</div>
                <div className="text-lg font-bold text-teal-800 mt-1">
                  ₹{costAnalytics.avg_cost_per_transport_trip_inr || '0.00'}
                </div>
                <div className="text-[11px] font-mono text-slate-500 mt-1">
                  {costAnalytics.avg_cost_per_transport_trip_paise || 0} paise / trip
                </div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-slate-500">Avg. Travel Cost per Verified Field Visit</div>
                <div className="text-lg font-bold text-indigo-800 mt-1">
                  ₹{costAnalytics.avg_cost_per_field_visit_inr || '0.00'}
                </div>
                <div className="text-[11px] font-mono text-slate-500 mt-1">
                  {costAnalytics.avg_cost_per_field_visit_paise || 0} paise / visit
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================
          SUBTAB 2: FUNDING CONTRACTS & MILESTONES
         =================================================================== */}
      {subTab === 'contracts' && (
        <div className="space-y-6">
          {isAdmin && (
            <form
              onSubmit={handleCreateDraftContract}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
            >
              <h3 className="text-sm font-bold text-slate-900">
                Create New Funding Contract Proposal (Starts in Unapproved Draft State)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <input
                  type="text"
                  required
                  placeholder="Programme Name"
                  value={newContractName}
                  onChange={(e) => setNewContractName(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <input
                  type="text"
                  required
                  placeholder="Contract Ref (e.g. MOU-NHM-2026-09)"
                  value={newContractRef}
                  onChange={(e) => setNewContractRef(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <input
                  type="number"
                  required
                  placeholder="Funding Ceiling (INR)"
                  value={newContractCeilingRupees}
                  onChange={(e) => setNewContractCeilingRupees(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <button
                  type="submit"
                  className="bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg px-4 py-2 cursor-pointer"
                >
                  + Create Draft Proposal
                </button>
              </div>
            </form>
          )}

          <div className="space-y-4">
            {contracts.map((c) => (
              <div
                key={c.id}
                className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold bg-slate-100 px-2.5 py-0.5 rounded">
                        {c.contract_reference}
                      </span>
                      <span
                        className={`text-xs font-bold uppercase px-2.5 py-0.5 rounded-full ${
                          c.state === 'active'
                            ? 'bg-emerald-100 text-emerald-800'
                            : c.state === 'draft' || c.state === 'submitted'
                            ? 'bg-amber-100 text-amber-900'
                            : 'bg-sky-100 text-sky-800'
                        }`}
                      >
                        {c.state}
                      </span>
                      <span className="text-xs text-slate-500">v{c.version_number}</span>
                    </div>
                    <h4 className="font-bold text-slate-900 text-base mt-1">{c.programme_name}</h4>
                    <div className="text-xs text-slate-600">
                      Funder: <strong>{c.funder_name}</strong> ({c.funder_type}) · Funder Share:{' '}
                      <strong>{c.funder_share_pct}</strong> · Basis: {c.reimbursement_basis}
                    </div>
                  </div>
                  <div className="text-right text-xs">
                    <div className="font-bold text-slate-900 text-sm">
                      Ceiling: ₹{c.funding_ceiling_inr}
                    </div>
                    <div className="text-emerald-700 font-semibold">
                      Received: ₹{c.funding_received_inr}
                    </div>
                    <div className="text-slate-500">
                      Period: {c.effective_from} → {c.effective_until}
                    </div>
                  </div>
                </div>

                {/* Mandatory Governance Disclaimer Banner */}
                <div
                  className={`p-2.5 rounded-xl text-xs font-medium flex items-center gap-2 ${
                    c.state === 'draft' || c.state === 'submitted'
                      ? 'bg-red-50 text-red-900 border border-red-200'
                      : 'bg-amber-50 text-amber-900 border border-amber-200'
                  }`}
                >
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{c.funding_status_banner}</span>
                </div>

                {/* State Transition Controls */}
                {isAdminOrDoc && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {c.state === 'draft' && (
                      <button
                        type="button"
                        onClick={() => handleTransitionContract(c.id, 'submitted')}
                        className="text-xs bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Submit Proposal for Review
                      </button>
                    )}
                    {c.state === 'submitted' && (
                      <button
                        type="button"
                        onClick={() => handleTransitionContract(c.id, 'approved')}
                        className="text-xs bg-teal-600 hover:bg-teal-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Record Simulated Approval
                      </button>
                    )}
                    {c.state === 'approved' && (
                      <button
                        type="button"
                        onClick={() => handleTransitionContract(c.id, 'active')}
                        className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Activate Contract
                      </button>
                    )}
                  </div>
                )}

                {/* Milestones */}
                {c.milestones && c.milestones.length > 0 && (
                  <div className="border-t border-slate-100 pt-2">
                    <div className="text-xs font-bold text-slate-700 mb-1.5">
                      Payment Milestones &amp; Tranches
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      {c.milestones.map((m: any) => (
                        <div
                          key={m.id}
                          className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 flex justify-between items-center"
                        >
                          <div>
                            <div className="font-semibold text-slate-900">{m.milestone_name}</div>
                            <div className="text-[11px] text-slate-500">
                              Due: {m.due_date} · Ref: {m.payment_reference || 'Pending'}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-bold">₹{m.tranche_amount_inr}</div>
                            <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-teal-100 text-teal-800 font-semibold">
                              {m.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ===================================================================
          SUBTAB 3: PROGRAMME BUDGETS & FINANCIAL CONTROL
         =================================================================== */}
      {subTab === 'budgets' && (
        <div className="space-y-6">
          {budgets.map((b) => (
            <div
              key={b.id}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">
                    Budget: {b.programme_name} ({b.fiscal_year}) — v{b.version_number}
                  </h3>
                  <p className="text-xs text-slate-500">
                    Scope: {b.budget_scope} ({b.target_clinic}) · Contract: {b.contract_reference}
                  </p>
                </div>
                <div className="text-right text-xs">
                  <div className="font-bold text-slate-900">
                    Total Allocated: ₹{b.totals?.allocated_inr}
                  </div>
                  <div className="text-teal-700 font-semibold">
                    Utilisation: {b.totals?.overall_utilisation_pct}
                  </div>
                </div>
              </div>

              {b.overspend_alerts && b.overspend_alerts.length > 0 && (
                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
                  {b.overspend_alerts.map((al: string, idx: number) => (
                    <div key={idx} className="flex items-center gap-1.5 font-semibold">
                      <AlertTriangle className="w-4 h-4 text-amber-700" />
                      <span>{al}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 uppercase text-slate-500">
                      <th className="py-2 px-2">Category</th>
                      <th className="py-2 px-2">Allocated (₹)</th>
                      <th className="py-2 px-2">Committed (₹)</th>
                      <th className="py-2 px-2">Incurred (₹)</th>
                      <th className="py-2 px-2">Approved (₹)</th>
                      <th className="py-2 px-2">Paid (₹)</th>
                      <th className="py-2 px-2">Reimbursed (₹)</th>
                      <th className="py-2 px-2">Available (₹)</th>
                      <th className="py-2 px-2">Util %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {(b.category_lines || []).map((ln: any) => (
                      <tr key={ln.id} className="hover:bg-slate-50">
                        <td className="py-2 px-2 font-sans font-semibold capitalize text-slate-900">
                          {ln.category.replace('_', ' ')}
                        </td>
                        <td className="py-2 px-2">₹{ln.allocated_inr}</td>
                        <td className="py-2 px-2 text-amber-700">₹{ln.committed_inr}</td>
                        <td className="py-2 px-2">₹{ln.incurred_inr}</td>
                        <td className="py-2 px-2 text-sky-700 font-semibold">
                          ₹{ln.approved_inr}
                        </td>
                        <td className="py-2 px-2 text-emerald-700">₹{ln.paid_inr}</td>
                        <td className="py-2 px-2 text-purple-700">₹{ln.reimbursed_inr}</td>
                        <td className="py-2 px-2 font-bold">₹{ln.available_inr}</td>
                        <td className="py-2 px-2">{ln.utilisation_pct}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {isAdmin && budgets.length > 0 && (
            <form
              onSubmit={handleAmendBudget}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
            >
              <h4 className="text-sm font-bold text-slate-900">
                Authorised Budget Category Amendment (Versioned &amp; Audited)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
                <select
                  value={amendBudgetId}
                  onChange={(e) => setAmendBudgetId(e.target.value)}
                  className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
                >
                  {budgets.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.programme_name} ({b.fiscal_year})
                    </option>
                  ))}
                </select>
                <select
                  value={amendCategory}
                  onChange={(e) => setAmendCategory(e.target.value)}
                  className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
                >
                  {[
                    'salary',
                    'travel',
                    'transport',
                    'clinical_services',
                    'diagnostics',
                    'technology',
                    'administration',
                  ].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  required
                  placeholder="New Allocation (INR)"
                  value={amendNewRupees}
                  onChange={(e) => setAmendNewRupees(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <input
                  type="text"
                  required
                  placeholder="Approval Ref (e.g. BGT-REV-02)"
                  value={amendRef}
                  onChange={(e) => setAmendRef(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <input
                  type="text"
                  required
                  placeholder="Amendment Reason"
                  value={amendReason}
                  onChange={(e) => setAmendReason(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
              </div>
              <button
                type="submit"
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-4 py-2 rounded-lg cursor-pointer"
              >
                Record Budget Amendment
              </button>
            </form>
          )}
        </div>
      )}

      {/* ===================================================================
          SUBTAB 4: WORKFORCE PAYROLL & PAYSLIPS
         =================================================================== */}
      {subTab === 'payroll' && (
        <div className="space-y-6">
          {isAdmin && (
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Monthly Healthcare Workforce Payroll Calculator
                </h3>
                <p className="text-xs text-slate-500">
                  Integrates Compensation Agreements, Shift Attendance, Approved Leave &amp;
                  Verified Field Visits. Prevents duplicate monthly payslips.
                </p>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <input
                  type="month"
                  value={payrollPeriod}
                  onChange={(e) => setPayrollPeriod(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <button
                  type="button"
                  onClick={handleCalculatePayroll}
                  className="bg-teal-700 hover:bg-teal-800 text-white font-semibold px-4 py-2 rounded-lg cursor-pointer"
                >
                  Calculate Monthly Payroll Run
                </button>
              </div>
            </div>
          )}

          {/* Statutory Config Notice */}
          {statutoryConfigs.length > 0 && (
            <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200 text-xs flex flex-wrap justify-between gap-2">
              <div>
                <strong>Active Validated Statutory Configuration:</strong>{' '}
                {statutoryConfigs[0].config_name} (v{statutoryConfigs[0].version_number})
              </div>
              <div className="text-slate-600">
                Validated by: <strong>{statutoryConfigs[0].validated_by_professional_name}</strong> (
                {statutoryConfigs[0].validated_by_credentials})
              </div>
            </div>
          )}

          {/* Payroll Runs (Admin) */}
          {isAdmin && payrollRuns.length > 0 && (
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
              <h4 className="text-sm font-bold text-slate-900">Payroll Batches &amp; Approval Workflow</h4>
              {payrollRuns.map((pr) => (
                <div
                  key={pr.id}
                  className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <div className="font-bold text-slate-900 text-sm">
                      Period: {pr.period_month} · Status:{' '}
                      <span className="uppercase text-teal-800">{pr.status}</span>
                    </div>
                    <div className="text-slate-600 mt-0.5">
                      Payslips: {pr.payslip_count} · Gross: ₹{pr.total_gross_inr} · Deductions: ₹
                      {pr.total_deductions_inr} · Net Payable:{' '}
                      <strong>₹{pr.total_net_payable_inr}</strong>
                    </div>
                    {pr.payment_batch_ref && (
                      <div className="text-[11px] font-mono text-emerald-800 mt-0.5">
                        Batch: {pr.payment_batch_ref} | Evidence: {pr.payment_evidence_ref}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {pr.status === 'draft' && (
                      <button
                        type="button"
                        onClick={() => handlePayrollTransition(pr.id, 'reviewed')}
                        className="bg-sky-600 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Mark Reviewed
                      </button>
                    )}
                    {pr.status === 'reviewed' && (
                      <button
                        type="button"
                        onClick={() => handlePayrollTransition(pr.id, 'approved')}
                        className="bg-teal-600 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Approve Payroll (Requires Different Reviewer)
                      </button>
                    )}
                    {pr.status === 'approved' && (
                      <button
                        type="button"
                        onClick={() => handlePayrollTransition(pr.id, 'locked')}
                        className="bg-amber-600 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Lock Payroll Batch
                      </button>
                    )}
                    {pr.status === 'locked' && (
                      <button
                        type="button"
                        onClick={() => handlePayrollTransition(pr.id, 'paid_verified')}
                        className="bg-emerald-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                      >
                        Confirm Paid with UTR Evidence
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Staff Compensation Agreements & Payslips */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h4 className="text-sm font-bold text-slate-900">
              Active Staff Compensation Agreements ({agreements.length})
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 uppercase text-slate-500">
                    <th className="py-2 px-2">Staff</th>
                    <th className="py-2 px-2">Employment Type</th>
                    <th className="py-2 px-2">Pay Structure</th>
                    <th className="py-2 px-2">Base Monthly</th>
                    <th className="py-2 px-2">Visit Rate</th>
                    <th className="py-2 px-2">Allowance</th>
                    <th className="py-2 px-2">Attendance Deduction Permitted?</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {agreements.map((ag) => (
                    <tr key={ag.id}>
                      <td className="py-2 px-2 font-semibold">{ag.staff_name}</td>
                      <td className="py-2 px-2">{ag.employment_type}</td>
                      <td className="py-2 px-2">{ag.pay_structure}</td>
                      <td className="py-2 px-2 font-mono">₹{ag.base_monthly_inr}</td>
                      <td className="py-2 px-2 font-mono">₹{ag.per_visit_rate_inr}</td>
                      <td className="py-2 px-2 font-mono">₹{ag.field_allowance_inr}</td>
                      <td className="py-2 px-2">
                        {ag.attendance_adjustment_permitted ? (
                          <span className="text-amber-800 font-semibold">Yes (Per Agreement)</span>
                        ) : (
                          <span className="text-slate-500">No (Protected Retainer)</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h4 className="text-sm font-bold text-slate-900">
              Generated Payslips ({payslips.length})
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 uppercase text-slate-500">
                    <th className="py-2 px-2">Period</th>
                    <th className="py-2 px-2">Staff</th>
                    <th className="py-2 px-2">Days Attended</th>
                    <th className="py-2 px-2">Visits</th>
                    <th className="py-2 px-2">Gross (₹)</th>
                    <th className="py-2 px-2">Deductions (₹)</th>
                    <th className="py-2 px-2">Net Payable (₹)</th>
                    <th className="py-2 px-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {payslips.map((sl) => (
                    <tr key={sl.id}>
                      <td className="py-2 px-2">{sl.period_month}</td>
                      <td className="py-2 px-2 font-sans font-semibold">{sl.staff_name}</td>
                      <td className="py-2 px-2">
                        {sl.days_attended}/{sl.days_scheduled}
                      </td>
                      <td className="py-2 px-2">{sl.completed_visits_count}</td>
                      <td className="py-2 px-2">₹{sl.gross_earnings_inr}</td>
                      <td className="py-2 px-2 text-red-700">₹{sl.total_deductions_inr}</td>
                      <td className="py-2 px-2 font-bold text-emerald-800">
                        ₹{sl.net_payable_inr}
                      </td>
                      <td className="py-2 px-2 font-sans uppercase">{sl.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================
          SUBTAB 5: EXPENSE CLAIMS & TRANSPORT RECONCILIATION
         =================================================================== */}
      {subTab === 'claims' && (
        <div className="space-y-6">
          <form
            onSubmit={handleSubmitClaim}
            className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
          >
            <h3 className="text-sm font-bold text-slate-900">
              Submit Travel / Transport Reimbursement Claim (Enforces Scheme Rules &amp; Duplicate
              Receipt Check)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-3 text-xs">
              <select
                value={claimCategory}
                onChange={(e) => setClaimCategory(e.target.value)}
                className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
              >
                <option value="travel">Staff Field Travel</option>
                <option value="transport">Patient Transport</option>
                <option value="clinical_services">Clinical Services</option>
                <option value="diagnostics">Diagnostics</option>
              </select>
              <select
                value={claimMode}
                onChange={(e) => setClaimMode(e.target.value)}
                className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
              >
                <option value="staff_two_wheeler_mileage">Two-Wheeler Mileage</option>
                <option value="empaneled_partner_van">Empaneled Partner Van</option>
                <option value="public_bus_rail">Public Bus / Rail</option>
                <option value="private_unapproved">Private Unapproved (Blocked by Default)</option>
              </select>
              <input
                type="number"
                placeholder="Distance (km)"
                value={claimDistanceKm}
                onChange={(e) => setClaimDistanceKm(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2"
              />
              <input
                type="number"
                required
                placeholder="Amount in Paise (e.g. 30000)"
                value={claimAmountPaise}
                onChange={(e) => setClaimAmountPaise(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2"
              />
              <input
                type="text"
                required
                placeholder="Receipt Number"
                value={claimReceiptNo}
                onChange={(e) => setClaimReceiptNo(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2"
              />
              <input
                type="text"
                required
                placeholder="Description"
                value={claimDesc}
                onChange={(e) => setClaimDesc(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2"
              />
            </div>
            <button
              type="submit"
              className="bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold px-4 py-2 rounded-lg cursor-pointer"
            >
              Submit Expense Claim
            </button>
          </form>

          {/* Claims List */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h4 className="text-sm font-bold text-slate-900">
              Expense Reimbursement Claims ({claims.length})
            </h4>
            <div className="space-y-2">
              {claims.map((ec) => (
                <div
                  key={ec.id}
                  className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <div className="font-bold text-slate-900">
                      {ec.receipt_number} — ₹{ec.amount_inr} ({ec.amount_paise} paise) ·{' '}
                      <span className="uppercase text-teal-800">{ec.status}</span>
                    </div>
                    <div className="text-slate-600 mt-0.5">
                      Category: {ec.expense_category} · Mode: {ec.transport_mode} · Claimant:{' '}
                      {ec.claimant_name}
                    </div>
                    <div className="text-slate-500">{ec.description}</div>
                  </div>
                  {isAdminOrDoc && (
                    <div className="flex flex-wrap gap-2">
                      {ec.status === 'submitted' && (
                        <button
                          type="button"
                          onClick={() => handleClaimDecision(ec.id, 'verified_by_supervisor')}
                          className="bg-sky-600 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                        >
                          Supervisor Verify
                        </button>
                      )}
                      {ec.status === 'verified_by_supervisor' && (
                        <button
                          type="button"
                          onClick={() => handleClaimDecision(ec.id, 'approved_by_finance')}
                          className="bg-teal-600 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                        >
                          Finance Approve
                        </button>
                      )}
                      {ec.status === 'approved_by_finance' && isAdmin && (
                        <button
                          type="button"
                          onClick={() => handleClaimDecision(ec.id, 'reimbursed_paid')}
                          className="bg-emerald-700 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                        >
                          Mark Reimbursed Paid
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Transport Trip to Expense Reconciliation */}
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h4 className="text-sm font-bold text-slate-900">
              Transport Trip-to-Expense Reconciliation
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 uppercase text-slate-500">
                    <th className="py-2 px-2">Trip ID</th>
                    <th className="py-2 px-2">Date</th>
                    <th className="py-2 px-2">Route</th>
                    <th className="py-2 px-2">Trip Status</th>
                    <th className="py-2 px-2">Trip Cost (₹)</th>
                    <th className="py-2 px-2">Receipt Ref</th>
                    <th className="py-2 px-2">Claim Reconciliation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(dashboard?.transport_reconciliation || []).map((tr: any) => (
                    <tr key={tr.trip_id}>
                      <td className="py-2 px-2 font-mono">{tr.trip_id}</td>
                      <td className="py-2 px-2">{tr.date}</td>
                      <td className="py-2 px-2">
                        {tr.from_location} → {tr.destination}
                      </td>
                      <td className="py-2 px-2 uppercase font-semibold">{tr.trip_status}</td>
                      <td className="py-2 px-2 font-mono">₹{tr.trip_expense_inr}</td>
                      <td className="py-2 px-2 font-mono">{tr.receipt_ref || '—'}</td>
                      <td className="py-2 px-2 font-semibold text-teal-800">{tr.claim_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================
          SUBTAB 6: SERVICE-TO-FUNDING EVIDENCE & PACKAGES
         =================================================================== */}
      {subTab === 'evidence' && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h3 className="text-sm font-bold text-slate-900">
              Submitted Institutional Funding Claims ({fundingClaims.length})
            </h3>
            {fundingClaims.length === 0 ? (
              <p className="text-xs text-slate-500">
                No funding claims yet. Click &ldquo;Run 12-Step Funded Programme Walkthrough&rdquo;
                above to generate a complete verified Service-to-Funding claim and Evidence Package.
              </p>
            ) : (
              <div className="space-y-2">
                {fundingClaims.map((fc) => (
                  <div
                    key={fc.id}
                    className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs"
                  >
                    <div>
                      <div className="font-bold text-slate-900 text-sm">
                        {fc.claim_reference} ({fc.programme_name}) —{' '}
                        <span className="uppercase text-teal-800">{fc.status}</span>
                      </div>
                      <div className="text-slate-600 mt-0.5">
                        Claimed: ₹{fc.total_claimed_inr} · Funder Reimbursable: ₹
                        {fc.funder_reimbursable_inr} · Settled: ₹{fc.approved_reimbursed_inr}
                      </div>
                      <div className="font-mono text-[11px] text-slate-500 mt-0.5">
                        SHA-256 Package Hash: {fc.evidence_package_hash}
                      </div>
                    </div>
                    {isAdminOrDoc && (
                      <button
                        type="button"
                        onClick={() => handleInspectEvidencePackage(fc.id)}
                        className="bg-slate-900 hover:bg-slate-800 text-white px-3.5 py-2 rounded-lg font-semibold cursor-pointer"
                      >
                        Inspect Privacy-Safe Evidence Package
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {selectedEvidencePkg && (
            <div className="bg-white rounded-2xl p-5 border-2 border-teal-600 shadow-sm space-y-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="bg-amber-100 text-amber-900 font-bold px-2.5 py-0.5 rounded-full text-[11px]">
                    {selectedEvidencePkg.compliance_label}
                  </span>
                  <h4 className="font-bold text-slate-900 text-base mt-1">
                    Supporting Evidence Package: {selectedEvidencePkg.funding_claim?.claim_reference}
                  </h4>
                </div>
                <div className="font-mono text-[11px] text-slate-500">
                  Hash: {selectedEvidencePkg.funding_claim?.evidence_package_hash?.slice(0, 24)}...
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-teal-50 text-teal-900 border border-teal-200">
                <strong>Privacy Safeguard:</strong> {selectedEvidencePkg.privacy_safeguard}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 uppercase text-slate-500">
                      <th className="py-2 px-2">Category</th>
                      <th className="py-2 px-2">Staff / Provider</th>
                      <th className="py-2 px-2">Anonymised Beneficiary</th>
                      <th className="py-2 px-2">Verification Evidence</th>
                      <th className="py-2 px-2">Expenditure Ref</th>
                      <th className="py-2 px-2">Amount (₹)</th>
                      <th className="py-2 px-2">Reimbursable (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(selectedEvidencePkg.evidence_chain || []).map((item: any) => (
                      <tr key={item.evidence_link_id}>
                        <td className="py-2 px-2 font-semibold capitalize">
                          {item.approved_service_category}
                        </td>
                        <td className="py-2 px-2">{item.assigned_staff_or_provider}</td>
                        <td className="py-2 px-2 font-mono text-teal-800 font-bold">
                          {item.beneficiary_anonymised_ref}
                        </td>
                        <td className="py-2 px-2 font-mono">{item.verification_evidence_ref}</td>
                        <td className="py-2 px-2 font-mono">{item.expenditure_receipt_ref}</td>
                        <td className="py-2 px-2 font-mono">₹{item.amount_inr}</td>
                        <td className="py-2 px-2 font-mono font-bold text-emerald-800">
                          ₹{item.funder_reimbursable_inr}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===================================================================
          SUBTAB 7: REPORTS & CSV/PDF EXPORTS
         =================================================================== */}
      {subTab === 'reports' && isAdminOrDoc && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-xs">
              <label className="font-bold text-slate-700">Select Report:</label>
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2 bg-white font-semibold"
              >
                <option value="contract_funding_summary">1. Contract Funding Summary</option>
                <option value="programme_budget_vs_actual">2. Programme Budget vs Actual</option>
                <option value="monthly_payroll_summary">3. Monthly Payroll Summary</option>
                <option value="staff_compensation_register">4. Staff Compensation Register</option>
                <option value="transport_field_expense_report">
                  5. Transport &amp; Field Expense Report
                </option>
                <option value="partner_service_expenditure_report">
                  6. Partner &amp; Service Expenditure Report
                </option>
                <option value="funder_utilisation_statement">
                  7. Funder Utilisation Statement
                </option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleDownloadExport(reportType, 'csv')}
                className="flex items-center gap-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-3.5 py-2 rounded-lg cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                Export CSV
              </button>
              <button
                type="button"
                onClick={() => handleDownloadExport(reportType, 'pdf')}
                className="flex items-center gap-1.5 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold px-3.5 py-2 rounded-lg cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                Export PDF
              </button>
            </div>
          </div>

          {reportData && (
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
              <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-xs font-bold text-amber-900">
                {reportData.compliance_watermark}
              </div>
              <h4 className="font-bold text-slate-900 text-sm">{reportData.title}</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 uppercase text-slate-500">
                      {(reportData.headers || []).map((h: string) => (
                        <th key={h} className="py-2 px-2">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {(reportData.rows || []).map((r: any[], idx: number) => (
                      <tr key={idx}>
                        {r.map((cell, cidx) => (
                          <td key={cidx} className="py-2 px-2">
                            {String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===================================================================
          SUBTAB 8: IMMUTABLE FINANCIAL AUDIT LEDGER & VERSIONED CORRECTIONS
         =================================================================== */}
      {subTab === 'audit' && isAdminOrDoc && (
        <div className="space-y-6">
          {isAdmin && (
            <form
              onSubmit={handleSubmitCorrection}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
            >
              <h3 className="text-sm font-bold text-slate-900">
                Record Versioned Financial Correction (No Destructive Overwrites)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
                <select
                  value={corrEntityType}
                  onChange={(e) => setCorrEntityType(e.target.value as any)}
                  className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
                >
                  <option value="expense_claim">Expense Claim</option>
                  <option value="payslip_record">Payslip Record</option>
                  <option value="expense">Expense</option>
                </select>
                <input
                  type="text"
                  required
                  placeholder="Entity ID"
                  value={corrEntityId}
                  onChange={(e) => setCorrEntityId(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <select
                  value={corrField}
                  onChange={(e) => setCorrField(e.target.value as any)}
                  className="border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
                >
                  <option value="amount_paise">amount_paise</option>
                  <option value="allowance_paise">allowance_paise</option>
                  <option value="description">description</option>
                  <option value="correction_note">correction_note</option>
                </select>
                <input
                  type="number"
                  placeholder="New Value (Paise)"
                  value={corrNewPaise}
                  onChange={(e) => setCorrNewPaise(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
                <input
                  type="text"
                  required
                  placeholder="Documented Correction Reason"
                  value={corrReason}
                  onChange={(e) => setCorrReason(e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2"
                />
              </div>
              <button
                type="submit"
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-4 py-2 rounded-lg cursor-pointer"
              >
                Apply Versioned Correction
              </button>
            </form>
          )}

          {corrections.length > 0 && (
            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-2">
              <h4 className="text-sm font-bold text-slate-900">
                Versioned Financial Corrections History ({corrections.length})
              </h4>
              {corrections.map((c) => (
                <div
                  key={c.id}
                  className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono"
                >
                  [v{c.version_number}] {c.entity_type}:{c.entity_id} · {c.field_name} (
                  {c.previous_value_paise ?? c.previous_text} →{' '}
                  {c.new_value_paise ?? c.new_text}) · Reason: {c.reason}
                </div>
              ))}
            </div>
          )}

          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3">
            <h4 className="text-sm font-bold text-slate-900">
              Append-Only Financial Audit Ledger ({auditLedger.length} entries)
            </h4>
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 uppercase text-slate-500">
                    <th className="py-2 px-2">Occurred</th>
                    <th className="py-2 px-2">Actor</th>
                    <th className="py-2 px-2">Action</th>
                    <th className="py-2 px-2">Entity</th>
                    <th className="py-2 px-2">Transition</th>
                    <th className="py-2 px-2">Amount (₹)</th>
                    <th className="py-2 px-2">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {auditLedger.map((entry) => (
                    <tr key={entry.id}>
                      <td className="py-2 px-2 text-slate-500">
                        {new Date(entry.occurred_at).toLocaleString()}
                      </td>
                      <td className="py-2 px-2">
                        {entry.actor_id} ({entry.actor_role})
                      </td>
                      <td className="py-2 px-2 font-bold text-teal-800">{entry.action}</td>
                      <td className="py-2 px-2">
                        {entry.entity_type}:{entry.entity_id}
                      </td>
                      <td className="py-2 px-2">
                        {entry.previous_state || '—'} → {entry.new_state || '—'}
                      </td>
                      <td className="py-2 px-2">₹{entry.amount_inr}</td>
                      <td className="py-2 px-2 text-slate-600">{entry.detail}</td>
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

