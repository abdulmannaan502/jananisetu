import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck,
  Users,
  Calendar,
  FileText,
  CheckSquare,
  MessageSquare,
  Truck,
  IndianRupee,
  BarChart3,
  UserCog,
  LogOut,
  AlertTriangle,
  CheckCircle2,
  Building2,
  Stethoscope,
  HeartHandshake,
  ClipboardList,
  Upload,
  RefreshCw,
  Lock,
} from 'lucide-react';
import { apiRequest, setStoredToken } from './api';
import AncDocumentReview from './components/AncDocumentReview';
import FollowupCommHub from './components/FollowupCommHub';
import WorkforceOperationsHub from './components/WorkforceOperationsHub';
import FinancialAccountabilityHub from './components/FinancialAccountabilityHub';
import type {
  StaffMember,
  Mother,
  CarePlan,
  TaskItem,
  MessageItem,
  TransportItem,
  ExpenseItem,
  DocumentItem,
  AuditEvent,
  ClinicAnalytics,
  RoleType,
} from './types';

type NavTab =
  | 'dashboard'
  | 'operations'
  | 'mothers'
  | 'appointments'
  | 'documents'
  | 'tasks'
  | 'messages'
  | 'transport'
  | 'staff'
  | 'expenses'
  | 'analytics';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Clinic Administrator',
  doctor: 'Medical Officer (Doctor)',
  nurse: 'ANM / Staff Nurse',
  field_coordinator: 'Field Coordinator (ASHA)',
  asha: 'Field Coordinator (ASHA)',
};

const ROLE_BADGE_COLORS: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-800 border-purple-200',
  doctor: 'bg-sky-100 text-sky-800 border-sky-200',
  nurse: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  field_coordinator: 'bg-amber-100 text-amber-800 border-amber-200',
};

export default function App() {
  const [currentUser, setCurrentUser] = useState<StaffMember | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(true);
  const [demoAccounts, setDemoAccounts] = useState<StaffMember[]>([]);
  const [demoPasswordHint, setDemoPasswordHint] = useState<string>('Janani@2026');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');

  // Login / Register state
  const [loginIdentifier, setLoginIdentifier] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regClinic, setRegClinic] = useState('');

  // Active Navigation & Notification state
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(false);

  // Live Backend State (NO hardcoded patient data)
  const [analytics, setAnalytics] = useState<ClinicAnalytics | null>(null);
  const [mothers, setMothers] = useState<Mother[]>([]);
  const [appointments, setAppointments] = useState<CarePlan[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [transports, setTransports] = useState<TransportItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [expenses, setExpenses] = useState<ExpenseItem[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);

  // Search & Filter states
  const [motherSearch, setMotherSearch] = useState('');
  const [selectedMotherForPlans, setSelectedMotherForPlans] = useState<string>('');
  const [motherPlans, setMotherPlans] = useState<CarePlan[]>([]);
  const [editedDocText, setEditedDocText] = useState<Record<string, string>>({});

  const notify = (text: string, type: 'success' | 'error' = 'success') => {
    setBanner({ text, type });
    setTimeout(() => {
      setBanner((prev) => (prev?.text === text ? null : prev));
    }, 5500);
  };

  const fetchDemoAccounts = useCallback(async () => {
    try {
      const res = await apiRequest<{ demo_password_hint: string; accounts: StaffMember[] }>(
        '/api/auth/demo-accounts?seed=true'
      );
      setDemoAccounts(res.accounts || []);
      if (res.demo_password_hint) setDemoPasswordHint(res.demo_password_hint);
    } catch {
      // Ignore on initial load
    }
  }, []);

  useEffect(() => {
    async function restoreSession() {
      try {
        const me = await apiRequest<StaffMember>('/api/auth/me');
        setCurrentUser(me);
      } catch {
        setStoredToken(null);
        await fetchDemoAccounts();
      } finally {
        setAuthLoading(false);
      }
    }
    restoreSession();
  }, [fetchDemoAccounts]);

  const loadClinicData = useCallback(async () => {
    if (!currentUser) return;
    setLoadingData(true);
    try {
      const role = currentUser.normalized_role;
      const [
        analyticsRes,
        mothersRes,
        apptsRes,
        tasksRes,
        msgsRes,
        transRes,
        docsRes,
        staffRes,
      ] = await Promise.all([
        apiRequest<ClinicAnalytics>('/api/analytics'),
        apiRequest<Mother[]>(
          motherSearch ? `/api/mothers?q=${encodeURIComponent(motherSearch)}` : '/api/mothers'
        ),
        apiRequest<CarePlan[]>('/api/appointments?active_only=false'),
        apiRequest<TaskItem[]>('/api/tasks'),
        apiRequest<MessageItem[]>('/api/messages'),
        apiRequest<TransportItem[]>('/api/transport'),
        apiRequest<DocumentItem[]>('/api/documents'),
        apiRequest<StaffMember[]>('/api/staff'),
      ]);

      setAnalytics(analyticsRes);
      setMothers(mothersRes);
      setAppointments(apptsRes);
      setTasks(tasksRes);
      setMessages(msgsRes);
      setTransports(transRes);
      setDocuments(docsRes);
      setStaffList(staffRes);

      if (mothersRes.length > 0 && !selectedMotherForPlans) {
        setSelectedMotherForPlans(mothersRes[0].id);
      }

      if (role === 'admin') {
        const expRes = await apiRequest<ExpenseItem[]>('/api/expenses');
        setExpenses(expRes);
      } else {
        setExpenses([]);
      }

      if (role === 'admin' || role === 'doctor') {
        const evRes = await apiRequest<AuditEvent[]>('/api/events?limit=80');
        setEvents(evRes);
      } else {
        setEvents([]);
      }
    } catch (err: any) {
      notify(err.message || 'Failed to load clinic records', 'error');
    } finally {
      setLoadingData(false);
    }
  }, [currentUser, motherSearch, selectedMotherForPlans]);

  useEffect(() => {
    if (currentUser) {
      loadClinicData();
    }
  }, [currentUser, loadClinicData]);

  useEffect(() => {
    async function loadPlansForMother() {
      if (!currentUser || !selectedMotherForPlans) {
        setMotherPlans([]);
        return;
      }
      try {
        const plans = await apiRequest<CarePlan[]>(`/api/mothers/${selectedMotherForPlans}/plans`);
        setMotherPlans(plans);
      } catch {
        setMotherPlans([]);
      }
    }
    loadPlansForMother();
  }, [currentUser, selectedMotherForPlans, appointments]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiRequest<{ access_token: string; staff: StaffMember }>(
        '/api/auth/login',
        'POST',
        { identifier: loginIdentifier, password: loginPassword }
      );
      setStoredToken(res.access_token);
      setCurrentUser(res.staff);
      setActiveTab('dashboard');
      notify(`Signed in as ${res.staff.name} (${res.staff.clinic})`);
    } catch (err: any) {
      notify(err.message || 'Authentication failed', 'error');
    }
  };

  const handleQuickDemoLogin = async (acc: StaffMember) => {
    try {
      const res = await apiRequest<{ access_token: string; staff: StaffMember }>(
        '/api/auth/login',
        'POST',
        { identifier: acc.email || acc.id, password: demoPasswordHint }
      );
      setStoredToken(res.access_token);
      setCurrentUser(res.staff);
      setActiveTab('dashboard');
      notify(`Switched to ${res.staff.name} [${res.staff.clinic}]`);
    } catch (err: any) {
      notify(err.message || 'Quick demo sign-in failed', 'error');
    }
  };

  const handleRegisterClinic = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiRequest<{ access_token: string; staff: StaffMember }>(
        '/api/auth/register',
        'POST',
        {
          name: regName,
          email: regEmail,
          password: regPassword,
          role: 'admin',
          clinic: regClinic,
        }
      );
      setStoredToken(res.access_token);
      setCurrentUser(res.staff);
      setActiveTab('dashboard');
      notify(`Registered new clinic "${res.staff.clinic}" and signed in as Administrator`);
    } catch (err: any) {
      notify(err.message || 'Registration failed', 'error');
    }
  };

  const handleLogout = async () => {
    try {
      await apiRequest('/api/auth/logout', 'POST');
    } catch {
      // ignore
    }
    setStoredToken(null);
    setCurrentUser(null);
    setSelectedMotherForPlans('');
    await fetchDemoAccounts();
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
        <div className="flex items-center gap-3 text-lg font-medium">
          <RefreshCw className="w-6 h-6 animate-spin text-teal-400" />
          Initializing JananiSetu Secure Care Platform...
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Unauthenticated View: Login + New Clinic Registration + Quick Role Switcher
  // ---------------------------------------------------------------------------
  if (!currentUser) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-teal-950 to-slate-900 text-slate-100 flex flex-col justify-between p-6">
        <header className="max-w-6xl w-full mx-auto flex flex-wrap items-center justify-between gap-4 border-b border-teal-800/60 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal-500/20 border border-teal-400/40 flex items-center justify-center text-teal-300 font-bold text-xl">
              ✦
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white">
                JananiSetu <span className="text-teal-400 font-normal text-lg">Care Operations</span>
              </h1>
              <p className="text-xs text-teal-200/80">
                Maternal Care Coordination & Multi-Clinic Operations · Health-a-thon 2026 Phase 2
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs bg-amber-500/15 border border-amber-400/30 text-amber-200 px-3 py-1.5 rounded-lg">
            <ShieldCheck className="w-4 h-4 text-amber-300 shrink-0" />
            <span>
              Assistive administration only · No autonomous diagnosis, risk scoring, or clinical decisions
            </span>
          </div>
        </header>

        <main className="max-w-6xl w-full mx-auto my-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left: Login / Clinic Registration Form */}
          <div className="lg:col-span-5 bg-white text-slate-900 rounded-2xl shadow-2xl p-7 border border-slate-200">
            <div className="flex gap-2 mb-6 bg-slate-100 p-1 rounded-xl">
              <button
                type="button"
                onClick={() => setAuthMode('login')}
                className={`flex-1 py-2 text-sm font-semibold rounded-lg transition ${
                  authMode === 'login'
                    ? 'bg-teal-700 text-white shadow'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Staff Sign In
              </button>
              <button
                type="button"
                onClick={() => setAuthMode('register')}
                className={`flex-1 py-2 text-sm font-semibold rounded-lg transition ${
                  authMode === 'register'
                    ? 'bg-teal-700 text-white shadow'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Register New Clinic
              </button>
            </div>

            {banner && (
              <div
                className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
                  banner.type === 'error'
                    ? 'bg-red-50 text-red-800 border border-red-200'
                    : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                }`}
              >
                {banner.type === 'error' ? (
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                )}
                <span>{banner.text}</span>
              </div>
            )}

            {authMode === 'login' ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Email or Staff ID
                  </label>
                  <input
                    type="text"
                    required
                    value={loginIdentifier}
                    onChange={(e) => setLoginIdentifier(e.target.value)}
                    placeholder="admin@nalgonda.janani.org"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-600 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-600 text-sm"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg shadow transition flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Lock className="w-4 h-4" />
                  Sign In with JWT Authentication
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegisterClinic} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Clinic / Facility Identifier
                  </label>
                  <input
                    type="text"
                    required
                    value={regClinic}
                    onChange={(e) => setRegClinic(e.target.value)}
                    placeholder="e.g. phc-khammam"
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Administrator Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={regName}
                    onChange={(e) => setRegName(e.target.value)}
                    placeholder="Dr. / Admin Name"
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Administrator Email
                  </label>
                  <input
                    type="email"
                    required
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="admin@khammam.janani.org"
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Password (min 6 chars)
                  </label>
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg shadow transition cursor-pointer"
                >
                  Create Isolated Clinic & Admin Account
                </button>
              </form>
            )}
          </div>

          {/* Right: Role-Based Evaluation Accounts (Live from Database) */}
          <div className="lg:col-span-7 bg-slate-800/80 border border-slate-700 rounded-2xl p-7">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Building2 className="w-5 h-5 text-teal-400" />
                One-Click Role & Multi-Clinic Evaluation Accounts
              </h2>
              <span className="text-xs bg-teal-500/20 text-teal-300 px-2.5 py-1 rounded-full font-mono">
                Password: {demoPasswordHint}
              </span>
            </div>
            <p className="text-xs text-slate-300 mb-5">
              Select any pre-seeded synthetic staff account below to authenticate via{' '}
              <code className="text-teal-300">POST /api/auth/login</code> and inspect its role-specific
              dashboard and clinic-isolated records.
            </p>

            <div className="space-y-5">
              {['demo-clinic', 'warangal-clinic'].map((clinicName) => {
                const clinicStaff = demoAccounts.filter((a) => a.clinic === clinicName);
                if (clinicStaff.length === 0) return null;
                return (
                  <div key={clinicName} className="bg-slate-900/70 rounded-xl p-4 border border-slate-700/80">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold uppercase tracking-wider text-teal-400">
                        Tenant Clinic: {clinicName}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        Strict data isolation enforced
                      </span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {clinicStaff.map((acc) => (
                        <button
                          key={acc.id}
                          type="button"
                          onClick={() => handleQuickDemoLogin(acc)}
                          className="text-left p-3 rounded-lg bg-slate-800 hover:bg-teal-900/50 border border-slate-700 hover:border-teal-500/60 transition group cursor-pointer"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-white group-hover:text-teal-300">
                              {acc.name}
                            </span>
                            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-teal-500/20 text-teal-300">
                              {acc.normalized_role.replace('_', ' ')}
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 mt-1 font-mono truncate">
                            {acc.email || acc.id}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </main>

        <footer className="max-w-6xl w-full mx-auto text-center text-xs text-slate-400 border-t border-slate-800 pt-4">
          JananiSetu v0.2.0 · Synthetic patient data only · All clinical care plans require licensed
          doctor authorisation.
        </footer>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Authenticated Role-Based Platform View
  // ---------------------------------------------------------------------------
  const userRole = currentUser.normalized_role;

  const navItems: { id: NavTab; label: string; icon: React.ReactNode; roles?: string[] }[] = [
    {
      id: 'dashboard',
      label: `${ROLE_LABELS[userRole]?.split(' ')[0] || 'Role'} Dashboard`,
      icon: <BarChart3 className="w-4 h-4" />,
    },
    {
      id: 'operations',
      label: 'Operations & Workforce',
      icon: <HeartHandshake className="w-4 h-4" />,
    },
    { id: 'mothers', label: 'Mothers & Consent', icon: <Users className="w-4 h-4" /> },
    { id: 'appointments', label: 'Care Plans & Visits', icon: <Calendar className="w-4 h-4" /> },
    { id: 'documents', label: 'ANC Scans & OCR', icon: <FileText className="w-4 h-4" /> },
    { id: 'tasks', label: 'Follow-up Tasks', icon: <CheckSquare className="w-4 h-4" /> },
    { id: 'messages', label: 'Reminders & Replies', icon: <MessageSquare className="w-4 h-4" /> },
    { id: 'transport', label: 'Transport Requests', icon: <Truck className="w-4 h-4" /> },
    {
      id: 'staff',
      label: 'Staff Management',
      icon: <UserCog className="w-4 h-4" />,
      roles: ['admin'],
    },
    {
      id: 'expenses',
      label: 'Contracts, Budgets & Finance',
      icon: <IndianRupee className="w-4 h-4" />,
    },
    {
      id: 'analytics',
      label: 'Analytics & Audit',
      icon: <ClipboardList className="w-4 h-4" />,
    },
  ];

  const visibleNav = navItems.filter((item) => !item.roles || item.roles.includes(userRole));

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Top Header */}
      <header className="bg-slate-900 text-white px-6 py-3.5 shadow-md flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-teal-500/20 border border-teal-400/40 flex items-center justify-center text-teal-300 font-bold">
            ✦
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-bold tracking-tight">JananiSetu</h1>
              <span className="text-xs bg-teal-800 text-teal-200 px-2.5 py-0.5 rounded-full font-medium border border-teal-600">
                Clinic: {currentUser.clinic}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Maternal Care Coordination · Synthetic Records Only · No Autonomous Clinical Decisions
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-semibold">{currentUser.name}</div>
            <div className="flex items-center justify-end gap-1.5">
              <span
                className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${
                  ROLE_BADGE_COLORS[userRole] || 'bg-slate-100 text-slate-800'
                }`}
              >
                {ROLE_LABELS[userRole] || currentUser.role}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => loadClinicData()}
            title="Refresh clinic data"
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loadingData ? 'animate-spin text-teal-400' : ''}`} />
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-xs font-semibold bg-red-600/90 hover:bg-red-700 text-white px-3 py-2 rounded-lg transition cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign Out
          </button>
        </div>
      </header>

      {/* Healthcare Safety Banner */}
      <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-xs text-amber-900 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-amber-700 shrink-0" />
          <span>
            <strong>Clinical Safety Governance:</strong> Care plans and visit dates can only be
            authorised by a licensed Doctor. OCR outputs require human verification. No AI diagnosis
            or risk scoring is performed.
          </span>
        </div>
        <span className="font-mono text-[11px] text-amber-700 shrink-0">
          Tenant Scope: {currentUser.clinic}
        </span>
      </div>

      {/* Main Layout */}
      <div className="flex-1 flex flex-col md:flex-row max-w-[1440px] w-full mx-auto">
        {/* Sidebar Navigation */}
        <aside className="w-full md:w-60 bg-white border-r border-slate-200 p-4 flex md:flex-col gap-1.5 overflow-x-auto shrink-0">
          {visibleNav.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition whitespace-nowrap cursor-pointer ${
                activeTab === item.id
                  ? 'bg-teal-700 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </aside>

        {/* View Content */}
        <main className="flex-1 p-6 overflow-y-auto space-y-6">
          {banner && (
            <div
              className={`p-3.5 rounded-xl text-sm font-medium flex items-center justify-between shadow-sm ${
                banner.type === 'error'
                  ? 'bg-red-50 text-red-800 border border-red-200'
                  : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              }`}
            >
              <div className="flex items-center gap-2">
                {banner.type === 'error' ? (
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                )}
                <span>{banner.text}</span>
              </div>
              <button
                type="button"
                onClick={() => setBanner(null)}
                className="text-xs underline ml-4 cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* ===============================================================
              TAB 1: ROLE-SPECIFIC DASHBOARDS (Admin, Doctor, Nurse, Field Coordinator)
             =============================================================== */}
          {activeTab === 'dashboard' && analytics && (
            <div className="space-y-6">
              {/* Role Header Card */}
              <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-teal-700">
                    {ROLE_LABELS[userRole]} Workspace · {currentUser.clinic}
                  </span>
                  <h2 className="text-2xl font-bold text-slate-900 mt-1">
                    Welcome, {currentUser.name}
                  </h2>
                  <p className="text-sm text-slate-600 mt-0.5">
                    {userRole === 'admin' &&
                      'Manage clinic staff credentials, approve programme expenditure, and audit clinic-wide operations.'}
                    {userRole === 'doctor' &&
                      'Authorise and version patient visit care plans, review ANC transcriptions, and oversee clinical follow-up.'}
                    {userRole === 'nurse' &&
                      'Register mothers, verify ANC card OCR transcriptions, trigger appointment reminders, and coordinate follow-ups.'}
                    {userRole === 'field_coordinator' &&
                      'Execute prioritized village outreach tasks, coordinate patient transport, and follow up on missed visits.'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setActiveTab('operations')}
                    className="px-3.5 py-2 bg-indigo-700 hover:bg-indigo-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                  >
                    Open Operations Centre & Workforce Hub
                  </button>
                  {userRole === 'admin' && (
                    <>
                      <button
                        onClick={() => setActiveTab('staff')}
                        className="px-3.5 py-2 bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Manage Clinic Staff
                      </button>
                      <button
                        onClick={() => setActiveTab('expenses')}
                        className="px-3.5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Approve Expenses
                      </button>
                    </>
                  )}
                  {userRole === 'doctor' && (
                    <button
                      onClick={() => setActiveTab('appointments')}
                      className="px-3.5 py-2 bg-sky-700 hover:bg-sky-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                    >
                      Authorise Care Plan
                    </button>
                  )}
                  {userRole === 'nurse' && (
                    <>
                      <button
                        onClick={() => setActiveTab('mothers')}
                        className="px-3.5 py-2 bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Register Mother
                      </button>
                      <button
                        onClick={() => setActiveTab('documents')}
                        className="px-3.5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Upload & Confirm ANC Scan
                      </button>
                    </>
                  )}
                  {userRole === 'field_coordinator' && (
                    <>
                      <button
                        onClick={() => setActiveTab('tasks')}
                        className="px-3.5 py-2 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Open Field Work Queue
                      </button>
                      <button
                        onClick={() => setActiveTab('transport')}
                        className="px-3.5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg cursor-pointer"
                      >
                        Coordinate Transport
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* KPI Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">Registered Mothers</span>
                  <div className="text-2xl font-bold text-slate-900 mt-1">
                    {analytics.registered_mothers}
                  </div>
                  <span className="text-[11px] text-emerald-700">
                    {analytics.consented_mothers} consented
                  </span>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">Active Care Plans</span>
                  <div className="text-2xl font-bold text-sky-700 mt-1">
                    {analytics.active_care_plans}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {analytics.upcoming_appointments} upcoming
                  </span>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">Overdue Visits</span>
                  <div className="text-2xl font-bold text-red-600 mt-1">
                    {analytics.overdue_plans}
                  </div>
                  <span className="text-[11px] text-red-600">Needs follow-up</span>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">Open Tasks</span>
                  <div className="text-2xl font-bold text-amber-600 mt-1">
                    {analytics.open_tasks}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {analytics.tasks_by_status?.resolved || 0} resolved
                  </span>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">ANC Scans</span>
                  <div className="text-2xl font-bold text-teal-700 mt-1">
                    {analytics.documents_total}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {analytics.documents_unconfirmed} unconfirmed
                  </span>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 font-medium">Transport Requests</span>
                  <div className="text-2xl font-bold text-indigo-700 mt-1">
                    {analytics.transport_requests}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {analytics.messages} messages logged
                  </span>
                </div>
              </div>

              {/* Role-Specific Action Panels */}
              {userRole === 'admin' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <UserCog className="w-4 h-4 text-purple-700" />
                        Clinic Staff Roster ({staffList.length})
                      </h3>
                      <button
                        onClick={() => setActiveTab('staff')}
                        className="text-xs text-teal-700 font-semibold hover:underline cursor-pointer"
                      >
                        Add / Edit Staff →
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100 text-sm">
                      {staffList.map((st) => (
                        <div key={st.id} className="py-2.5 flex items-center justify-between">
                          <div>
                            <div className="font-medium text-slate-900">{st.name}</div>
                            <div className="text-xs text-slate-500">{st.email || st.id}</div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-xs px-2 py-0.5 rounded-full border ${
                                ROLE_BADGE_COLORS[st.normalized_role] || 'bg-slate-100'
                              }`}
                            >
                              {st.normalized_role}
                            </span>
                            <span
                              className={`text-[11px] px-2 py-0.5 rounded ${
                                st.is_active
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : 'bg-red-50 text-red-700'
                              }`}
                            >
                              {st.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <IndianRupee className="w-4 h-4 text-teal-700" />
                        Operational Expenditure Summary
                      </h3>
                      <button
                        onClick={() => setActiveTab('expenses')}
                        className="text-xs text-teal-700 font-semibold hover:underline cursor-pointer"
                      >
                        Manage Ledger →
                      </button>
                    </div>
                    <div className="grid grid-cols-3 gap-3 mb-4">
                      <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                        <div className="text-xs text-slate-500">Total Recorded</div>
                        <div className="text-lg font-bold">
                          ₹{(analytics.expenses_total_paise / 100).toLocaleString()}
                        </div>
                      </div>
                      <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200">
                        <div className="text-xs text-emerald-700">Approved</div>
                        <div className="text-lg font-bold text-emerald-800">
                          ₹{(analytics.expenses_approved_paise / 100).toLocaleString()}
                        </div>
                      </div>
                      <div className="p-3 rounded-lg bg-amber-50 border border-amber-200">
                        <div className="text-xs text-amber-700">Pending Approval</div>
                        <div className="text-lg font-bold text-amber-800">
                          ₹{(analytics.expenses_pending_paise / 100).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div className="space-y-2 text-xs">
                      {expenses.slice(0, 4).map((e) => (
                        <div
                          key={e.id}
                          className="flex items-center justify-between p-2 rounded bg-slate-50"
                        >
                          <span>
                            <strong className="uppercase">{e.category}</strong> · {e.description}
                          </span>
                          <span className="font-semibold">
                            ₹{e.amount_rupees} ({e.approved ? 'Approved' : 'Pending'})
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {userRole === 'doctor' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <Stethoscope className="w-4 h-4 text-sky-700" />
                        Active & Overdue Patient Appointments
                      </h3>
                      <button
                        onClick={() => setActiveTab('appointments')}
                        className="text-xs text-sky-700 font-semibold hover:underline cursor-pointer"
                      >
                        Authorise Care Plans →
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100 text-sm">
                      {appointments.slice(0, 6).map((ap) => (
                        <div key={ap.id} className="py-2.5 flex items-center justify-between">
                          <div>
                            <div className="font-medium text-slate-900">
                              {ap.mother_name || ap.mother_id}{' '}
                              <span className="text-xs text-slate-500">v{ap.version}</span>
                            </div>
                            <div className="text-xs text-slate-500">{ap.note || ap.visit_type}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs font-semibold">{ap.visit_date}</div>
                            <span
                              className={`text-[11px] px-2 py-0.5 rounded-full ${
                                ap.appointment_status === 'missed' || ap.is_overdue
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-sky-100 text-sky-800'
                              }`}
                            >
                              {ap.appointment_status}
                            </span>
                          </div>
                        </div>
                      ))}
                      {appointments.length === 0 && (
                        <p className="text-xs text-slate-500 py-4">No appointments scheduled yet.</p>
                      )}
                    </div>
                  </div>

                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-teal-700" />
                        ANC Card OCR Reviews ({analytics.documents_unconfirmed} Unconfirmed)
                      </h3>
                      <button
                        onClick={() => setActiveTab('documents')}
                        className="text-xs text-teal-700 font-semibold hover:underline cursor-pointer"
                      >
                        Review Scans →
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100 text-sm">
                      {documents.slice(0, 5).map((d) => (
                        <div key={d.id} className="py-2.5 flex items-center justify-between">
                          <div>
                            <div className="font-medium">{d.mother_name || d.mother_id}</div>
                            <div className="text-xs text-slate-500 truncate max-w-xs">
                              {d.extracted_text}
                            </div>
                          </div>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                              d.confirmed
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {d.confirmed ? 'Confirmed' : 'Needs Review'}
                          </span>
                        </div>
                      ))}
                      {documents.length === 0 && (
                        <p className="text-xs text-slate-500 py-4">No ANC scans uploaded yet.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {(userRole === 'nurse' || userRole === 'field_coordinator') && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <HeartHandshake className="w-4 h-4 text-amber-600" />
                        Prioritized Follow-up & Outreach Queue
                      </h3>
                      <button
                        onClick={() => setActiveTab('tasks')}
                        className="text-xs text-teal-700 font-semibold hover:underline cursor-pointer"
                      >
                        Full Queue →
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100 text-sm">
                      {tasks
                        .filter((t) => t.status !== 'resolved' && t.status !== 'cancelled')
                        .slice(0, 6)
                        .map((t) => (
                          <div key={t.id} className="py-2.5 flex items-center justify-between gap-2">
                            <div>
                              <div className="font-medium text-slate-900">
                                {t.mother_name || t.mother_id} ·{' '}
                                <span className="text-xs uppercase font-semibold text-teal-700">
                                  {t.category.replace('_', ' ')}
                                </span>
                              </div>
                              <div className="text-xs text-slate-500">{t.detail}</div>
                            </div>
                            <div className="text-right shrink-0">
                              <span
                                className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                                  t.priority === 'urgent' || t.priority === 'high'
                                    ? 'bg-red-100 text-red-800'
                                    : 'bg-amber-100 text-amber-800'
                                }`}
                              >
                                {t.priority}
                              </span>
                              <div className="text-[11px] text-slate-400 mt-0.5">
                                {t.assigned_to_name}
                              </div>
                            </div>
                          </div>
                        ))}
                      {tasks.length === 0 && (
                        <p className="text-xs text-slate-500 py-4">No active follow-up tasks.</p>
                      )}
                    </div>
                  </div>

                  <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <Truck className="w-4 h-4 text-indigo-700" />
                        Upcoming Transport Coordination
                      </h3>
                      <button
                        onClick={() => setActiveTab('transport')}
                        className="text-xs text-teal-700 font-semibold hover:underline cursor-pointer"
                      >
                        Manage Requests →
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100 text-sm">
                      {transports.slice(0, 5).map((tr) => (
                        <div key={tr.id} className="py-2.5 flex items-center justify-between">
                          <div>
                            <div className="font-medium">{tr.mother_name || tr.mother_id}</div>
                            <div className="text-xs text-slate-500">
                              {tr.from_location} → {tr.destination} ({tr.partner})
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs font-semibold">
                              {tr.date} · {tr.pickup_time}
                            </div>
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                              {tr.status}
                            </span>
                          </div>
                        </div>
                      ))}
                      {transports.length === 0 && (
                        <p className="text-xs text-slate-500 py-4">No transport requests logged.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===============================================================
              TAB 2: MOTHERS REGISTRATION & CONSENT MANAGEMENT
             =============================================================== */}
          {activeTab === 'mothers' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm h-fit">
                <h2 className="text-lg font-bold text-slate-900 mb-1">
                  Register Synthetic Patient
                </h2>
                <p className="text-xs text-slate-500 mb-4">
                  Records are strictly isolated to clinic <strong>{currentUser.clinic}</strong>.
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      await apiRequest('/api/mothers', 'POST', {
                        name: String(fd.get('name') || ''),
                        phone: String(fd.get('phone') || ''),
                        language: String(fd.get('language') || 'te'),
                        age: fd.get('age') ? Number(fd.get('age')) : null,
                        lmp: fd.get('lmp') ? String(fd.get('lmp')) : null,
                        edd: fd.get('edd') ? String(fd.get('edd')) : null,
                        address: String(fd.get('address') || ''),
                        notes: String(fd.get('notes') || ''),
                        consent: fd.get('consent') === 'on',
                      });
                      e.currentTarget.reset();
                      notify('Synthetic mother record registered');
                      await loadClinicData();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Full Name (Synthetic) *
                    </label>
                    <input
                      name="name"
                      required
                      placeholder="e.g. Swapna Kumari (Synthetic)"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Phone Number *
                      </label>
                      <input
                        name="phone"
                        required
                        placeholder="9800000199"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Age (Years)
                      </label>
                      <input
                        name="age"
                        type="number"
                        min={14}
                        max={60}
                        placeholder="24"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Preferred Language
                    </label>
                    <select
                      name="language"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    >
                      <option value="te">Telugu (తెలుగు)</option>
                      <option value="hi">Hindi (हिन्दी)</option>
                      <option value="en">English</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Recorded LMP Date
                      </label>
                      <input
                        name="lmp"
                        type="date"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Clinician EDD Date
                      </label>
                      <input
                        name="edd"
                        type="date"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Village / Ward Address
                    </label>
                    <input
                      name="address"
                      placeholder="Sector / Village name"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Administrative Notes
                    </label>
                    <textarea
                      name="notes"
                      rows={2}
                      placeholder="Care coordination notes"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <label className="flex items-center gap-2 pt-1 cursor-pointer">
                    <input name="consent" type="checkbox" defaultChecked className="w-4 h-4" />
                    <span className="text-xs font-semibold text-slate-700">
                      Patient communication consent recorded
                    </span>
                  </label>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg transition cursor-pointer"
                  >
                    Register Mother
                  </button>
                </form>
              </div>

              <div className="lg:col-span-8 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <h2 className="text-lg font-bold text-slate-900">
                    Registered Mothers ({mothers.length})
                  </h2>
                  <input
                    type="search"
                    value={motherSearch}
                    onChange={(e) => setMotherSearch(e.target.value)}
                    placeholder="Search by name or phone..."
                    className="px-3 py-1.5 rounded-lg border border-slate-300 text-sm w-64"
                  />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                        <th className="py-2.5 px-2">Name & Address</th>
                        <th className="py-2.5 px-2">Phone / Lang</th>
                        <th className="py-2.5 px-2">LMP / EDD</th>
                        <th className="py-2.5 px-2">Next Visit</th>
                        <th className="py-2.5 px-2">Consent</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {mothers.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-50">
                          <td className="py-3 px-2">
                            <div className="font-semibold text-slate-900">
                              {m.name}{' '}
                              {m.age ? (
                                <span className="text-xs font-normal text-slate-500">
                                  ({m.age}y)
                                </span>
                              ) : null}
                            </div>
                            <div className="text-xs text-slate-500">{m.address || m.id}</div>
                          </td>
                          <td className="py-3 px-2">
                            <div className="font-mono text-xs">{m.phone}</div>
                            <span className="text-[11px] uppercase bg-slate-100 px-1.5 py-0.5 rounded">
                              {m.language}
                            </span>
                          </td>
                          <td className="py-3 px-2 text-xs text-slate-600">
                            <div>LMP: {m.lmp || '—'}</div>
                            <div>EDD: {m.edd || '—'}</div>
                          </td>
                          <td className="py-3 px-2 text-xs">
                            {m.next_visit_date ? (
                              <div>
                                <div className="font-semibold">{m.next_visit_date}</div>
                                <span className="text-[11px] text-teal-700">
                                  {m.appointment_status}
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-400">No active plan</span>
                            )}
                          </td>
                          <td className="py-3 px-2">
                            <button
                              type="button"
                              onClick={async () => {
                                try {
                                  await apiRequest(`/api/mothers/${m.id}/consent`, 'PATCH', {
                                    consent: !m.consent,
                                  });
                                  notify(
                                    `Updated consent for ${m.name} to ${!m.consent ? 'Granted' : 'Revoked'}`
                                  );
                                  await loadClinicData();
                                } catch (err: any) {
                                  notify(err.message, 'error');
                                }
                              }}
                              className={`text-xs px-2.5 py-1 rounded-full font-semibold cursor-pointer ${
                                m.consent
                                  ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                                  : 'bg-red-100 text-red-800 hover:bg-red-200'
                              }`}
                            >
                              {m.consent ? 'Consented ✓' : 'No Consent ✕'}
                            </button>
                          </td>
                        </tr>
                      ))}
                      {mothers.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-slate-400">
                            No mothers registered in this clinic yet.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ===============================================================
              TAB 3: DOCTOR-AUTHORISED CARE PLANS & APPOINTMENT SCHEDULING
             =============================================================== */}
          {activeTab === 'appointments' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Authorise New Care Plan (Doctor only) */}
                <div className="lg:col-span-5 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-lg font-bold text-slate-900">
                      Doctor-Authorised Care Plan
                    </h2>
                    <span className="text-xs px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-semibold">
                      Doctor Role Required
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mb-4">
                    Each new plan automatically increments the version and supersedes prior active
                    plans for that mother.
                  </p>

                  {userRole !== 'doctor' ? (
                    <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900">
                      You are signed in as <strong>{ROLE_LABELS[userRole]}</strong>. Only licensed
                      doctors can create or revise clinical care plans. You can view plans and
                      update appointment attendance status on the right.
                    </div>
                  ) : (
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const fd = new FormData(e.currentTarget);
                        const mid = String(fd.get('mother_id') || '');
                        try {
                          await apiRequest(`/api/mothers/${mid}/plans`, 'POST', {
                            visit_date: String(fd.get('visit_date') || ''),
                            visit_type: String(fd.get('visit_type') || 'anc_checkup'),
                            note: String(fd.get('note') || ''),
                          });
                          notify('New care plan version authorised and activated');
                          setSelectedMotherForPlans(mid);
                          await loadClinicData();
                        } catch (err: any) {
                          notify(err.message, 'error');
                        }
                      }}
                      className="space-y-3 text-sm"
                    >
                      <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">
                          Select Mother *
                        </label>
                        <select
                          name="mother_id"
                          required
                          value={selectedMotherForPlans}
                          onChange={(e) => setSelectedMotherForPlans(e.target.value)}
                          className="w-full px-3 py-2 rounded-lg border border-slate-300"
                        >
                          {mothers.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name} ({m.phone})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 mb-1">
                            Next Visit Date *
                          </label>
                          <input
                            name="visit_date"
                            type="date"
                            required
                            className="w-full px-3 py-2 rounded-lg border border-slate-300"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 mb-1">
                            Visit Type
                          </label>
                          <select
                            name="visit_type"
                            className="w-full px-3 py-2 rounded-lg border border-slate-300"
                          >
                            <option value="anc_checkup">ANC Checkup</option>
                            <option value="follow_up">Follow-up Visit</option>
                            <option value="ultrasound_review">Ultrasound Review</option>
                            <option value="lab_review">Lab Review</option>
                            <option value="postnatal">Postnatal Check</option>
                            <option value="other">Other</option>
                          </select>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">
                          Doctor&apos;s Administrative Instruction
                        </label>
                        <textarea
                          name="note"
                          rows={3}
                          placeholder="Enter visit preparation or follow-up instructions..."
                          className="w-full px-3 py-2 rounded-lg border border-slate-300"
                        />
                      </div>
                      <button
                        type="submit"
                        className="w-full py-2.5 bg-sky-700 hover:bg-sky-800 text-white font-semibold rounded-lg transition cursor-pointer"
                      >
                        Approve & Version Care Plan
                      </button>
                    </form>
                  )}

                  {/* Version History for Selected Mother */}
                  <div className="mt-6 pt-5 border-t border-slate-200">
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-bold uppercase text-slate-500">
                        Plan Version History
                      </label>
                      <select
                        value={selectedMotherForPlans}
                        onChange={(e) => setSelectedMotherForPlans(e.target.value)}
                        className="text-xs border border-slate-300 rounded px-2 py-1"
                      >
                        {mothers.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2 max-h-56 overflow-y-auto text-xs">
                      {motherPlans.map((p) => (
                        <div
                          key={p.id}
                          className={`p-2.5 rounded-lg border ${
                            p.active
                              ? 'bg-sky-50 border-sky-200'
                              : 'bg-slate-50 border-slate-200 opacity-75'
                          }`}
                        >
                          <div className="flex items-center justify-between font-semibold">
                            <span>
                              v{p.version} · Visit: {p.visit_date} ({p.visit_type})
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] ${
                                p.active
                                  ? 'bg-sky-700 text-white'
                                  : 'bg-slate-200 text-slate-700'
                              }`}
                            >
                              {p.active ? 'ACTIVE' : 'SUPERSEDED'}
                            </span>
                          </div>
                          <div className="text-slate-600 mt-1">{p.note || 'No note'}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Clinic-Wide Appointment Schedule & Follow-up Lifecycle */}
                <div className="lg:col-span-7 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                  <h2 className="text-lg font-bold text-slate-900 mb-1">
                    Appointment Schedule & Attendance Follow-up
                  </h2>
                  <p className="text-xs text-slate-500 mb-4">
                    Update appointment outcomes or mark missed visits to automatically generate a
                    high-priority field follow-up task.
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                          <th className="py-2 px-2">Mother</th>
                          <th className="py-2 px-2">Visit Date</th>
                          <th className="py-2 px-2">Doctor Note</th>
                          <th className="py-2 px-2">Status</th>
                          <th className="py-2 px-2">Follow-up Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {appointments
                          .filter((a) => a.active)
                          .map((ap) => (
                            <tr key={ap.id} className="hover:bg-slate-50">
                              <td className="py-3 px-2">
                                <div className="font-semibold text-slate-900">
                                  {ap.mother_name || ap.mother_id}
                                </div>
                                <div className="text-xs text-slate-500">
                                  v{ap.version} · {ap.visit_type}
                                </div>
                              </td>
                              <td className="py-3 px-2 text-xs font-semibold">
                                <div>{ap.visit_date}</div>
                                {ap.is_overdue && (
                                  <span className="text-[10px] text-red-600 font-bold">
                                    OVERDUE
                                  </span>
                                )}
                              </td>
                              <td className="py-3 px-2 text-xs text-slate-600 max-w-xs">
                                {ap.note}
                              </td>
                              <td className="py-3 px-2">
                                <span
                                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                    ap.appointment_status === 'completed'
                                      ? 'bg-emerald-100 text-emerald-800'
                                      : ap.appointment_status === 'missed'
                                      ? 'bg-red-100 text-red-800'
                                      : 'bg-sky-100 text-sky-800'
                                  }`}
                                >
                                  {ap.appointment_status}
                                </span>
                              </td>
                              <td className="py-3 px-2">
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    onClick={async () => {
                                      try {
                                        await apiRequest(`/api/appointments/${ap.id}`, 'PATCH', {
                                          appointment_status: 'completed',
                                          follow_up_notes: 'Completed clinic visit',
                                        });
                                        notify('Marked appointment as completed');
                                        await loadClinicData();
                                      } catch (err: any) {
                                        notify(err.message, 'error');
                                      }
                                    }}
                                    className="px-2 py-1 text-xs rounded bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer"
                                  >
                                    Complete
                                  </button>
                                  <button
                                    type="button"
                                    onClick={async () => {
                                      try {
                                        await apiRequest(`/api/appointments/${ap.id}`, 'PATCH', {
                                          appointment_status: 'missed',
                                          follow_up_notes: 'Missed scheduled visit',
                                          create_followup_task: true,
                                        });
                                        notify(
                                          'Marked missed & auto-created field follow-up task'
                                        );
                                        await loadClinicData();
                                      } catch (err: any) {
                                        notify(err.message, 'error');
                                      }
                                    }}
                                    className="px-2 py-1 text-xs rounded bg-red-600 hover:bg-red-700 text-white cursor-pointer"
                                  >
                                    Missed + Task
                                  </button>
                                </div>
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

          {/* ===============================================================
              TAB 4: ANC DOCUMENT UPLOADS & EVIDENCE-LINKED VERIFICATION
             =============================================================== */}
          {activeTab === 'documents' && (
            <AncDocumentReview
              mothers={mothers}
              documents={documents}
              userRole={userRole}
              onRefreshClinicData={loadClinicData}
              notify={notify}
            />
          )}

          {/* ===============================================================
              TAB 5: TASK ASSIGNMENT & COMPLETION
             =============================================================== */}
          {activeTab === 'tasks' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm h-fit">
                <h2 className="text-lg font-bold text-slate-900 mb-1">Assign Follow-up Task</h2>
                <p className="text-xs text-slate-500 mb-4">
                  Assign field visits, missed-visit outreach, or transport checks to clinic staff.
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      await apiRequest('/api/tasks', 'POST', {
                        mother_id: String(fd.get('mother_id') || ''),
                        category: String(fd.get('category') || 'contact_attempt'),
                        priority: String(fd.get('priority') || 'medium'),
                        due_date: fd.get('due_date') ? String(fd.get('due_date')) : null,
                        assigned_to: String(fd.get('assigned_to') || ''),
                        detail: String(fd.get('detail') || ''),
                      });
                      e.currentTarget.reset();
                      notify('Follow-up task created');
                      await loadClinicData();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Mother *
                    </label>
                    <select
                      name="mother_id"
                      required
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    >
                      {mothers.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Category
                      </label>
                      <select
                        name="category"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      >
                        <option value="contact_attempt">Contact Attempt</option>
                        <option value="missed_visit">Missed Visit</option>
                        <option value="home_visit">Home Visit</option>
                        <option value="patient_reply">Patient Reply</option>
                        <option value="transport">Transport</option>
                        <option value="document_followup">Document Follow-up</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Priority
                      </label>
                      <select
                        name="priority"
                        defaultValue="medium"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="urgent">Urgent</option>
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Assign To Staff
                      </label>
                      <select
                        name="assigned_to"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      >
                        <option value="">Unassigned</option>
                        {staffList.map((st) => (
                          <option key={st.id} value={st.id}>
                            {st.name} ({st.normalized_role})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Due Date
                      </label>
                      <input
                        name="due_date"
                        type="date"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Task Instructions
                    </label>
                    <textarea
                      name="detail"
                      rows={3}
                      required
                      placeholder="Describe required follow-up action..."
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg transition cursor-pointer"
                  >
                    Create Task
                  </button>
                </form>
              </div>

              <div className="lg:col-span-8 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-slate-900 mb-4">
                  Clinic Work Queue ({tasks.length})
                </h2>
                <div className="space-y-3">
                  {tasks.map((t) => (
                    <div
                      key={t.id}
                      className="p-4 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-4 bg-white hover:bg-slate-50"
                    >
                      <div className="space-y-1 max-w-xl">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-900">
                            {t.mother_name || t.mother_id}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded bg-slate-100 font-semibold uppercase">
                            {t.category.replace('_', ' ')}
                          </span>
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                              t.priority === 'urgent' || t.priority === 'high'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {t.priority}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600">{t.detail}</p>
                        <div className="text-[11px] text-slate-400">
                          Assigned to: <strong>{t.assigned_to_name}</strong>
                          {t.due_date ? ` · Due: ${t.due_date}` : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={t.status}
                          onChange={async (e) => {
                            const newStatus = e.target.value;
                            try {
                              await apiRequest(`/api/tasks/${t.id}`, 'PATCH', {
                                status: newStatus,
                              });
                              notify(`Task ${t.id} updated to ${newStatus}`);
                              await loadClinicData();
                            } catch (err: any) {
                              notify(err.message, 'error');
                            }
                          }}
                          className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 font-semibold bg-white"
                        >
                          <option value="open">Open</option>
                          <option value="in_progress">In Progress</option>
                          <option value="resolved">Resolved</option>
                          <option value="cancelled">Cancelled</option>
                        </select>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ===============================================================
              TAB 6: PHASE 4 CLOSED-LOOP FOLLOW-UP & COMMUNICATION ENGINE
             =============================================================== */}
          {activeTab === 'messages' && (
            <FollowupCommHub
              currentUser={currentUser}
              mothers={mothers}
              appointments={appointments}
              tasks={tasks}
              messages={messages}
              onRefreshParent={loadClinicData}
              notify={notify}
            />
          )}

          {/* ===============================================================
              TAB 7: TRANSPORT COORDINATION
             =============================================================== */}
          {activeTab === 'transport' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm h-fit">
                <h2 className="text-lg font-bold text-slate-900 mb-1">Request Patient Transport</h2>
                <p className="text-xs text-slate-500 mb-4">
                  Administrative transport coordination log (does not dispatch emergency ambulances).
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      await apiRequest('/api/transport', 'POST', {
                        mother_id: String(fd.get('mother_id') || ''),
                        date: String(fd.get('date') || ''),
                        pickup_time: String(fd.get('pickup_time') || '09:00'),
                        from_location: String(fd.get('from_location') || ''),
                        destination: String(fd.get('destination') || ''),
                        partner: String(fd.get('partner') || 'not assigned'),
                        vehicle_notes: String(fd.get('vehicle_notes') || ''),
                      });
                      e.currentTarget.reset();
                      notify('Transport request recorded');
                      await loadClinicData();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Mother *
                    </label>
                    <select
                      name="mother_id"
                      required
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    >
                      {mothers.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Pickup Date *
                      </label>
                      <input
                        name="date"
                        type="date"
                        required
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Pickup Time
                      </label>
                      <input
                        name="pickup_time"
                        defaultValue="09:00"
                        className="w-full px-3 py-2 rounded-lg border border-slate-300"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Pickup Origin *
                    </label>
                    <input
                      name="from_location"
                      required
                      placeholder="Village / Ward"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Destination Facility *
                    </label>
                    <input
                      name="destination"
                      required
                      placeholder="PHC / CHC Facility"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Approved Transport Partner
                    </label>
                    <input
                      name="partner"
                      placeholder="e.g. 102 Janani Express Partner"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Vehicle / Driver Notes
                    </label>
                    <input
                      name="vehicle_notes"
                      placeholder="Optional vehicle details"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg transition cursor-pointer"
                  >
                    Record Transport Request
                  </button>
                </form>
              </div>

              <div className="lg:col-span-8 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-slate-900 mb-4">
                  Clinic Transport Schedule ({transports.length})
                </h2>
                <div className="space-y-3">
                  {transports.map((tr) => (
                    <div
                      key={tr.id}
                      className="p-4 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-4"
                    >
                      <div>
                        <div className="font-bold text-sm">
                          {tr.mother_name || tr.mother_id} ·{' '}
                          <span className="text-teal-700">
                            {tr.date} @ {tr.pickup_time}
                          </span>
                        </div>
                        <div className="text-xs text-slate-600 mt-0.5">
                          {tr.from_location} → <strong>{tr.destination}</strong>
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5">
                          Partner: {tr.partner} {tr.vehicle_notes ? `· ${tr.vehicle_notes}` : ''}
                        </div>
                      </div>
                      <select
                        value={tr.status}
                        onChange={async (e) => {
                          try {
                            await apiRequest(`/api/transport/${tr.id}`, 'PATCH', {
                              status: e.target.value,
                            });
                            notify(`Transport status updated to ${e.target.value}`);
                            await loadClinicData();
                          } catch (err: any) {
                            notify(err.message, 'error');
                          }
                        }}
                        className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 font-semibold"
                      >
                        <option value="requested">Requested</option>
                        <option value="assigned">Assigned</option>
                        <option value="in_transit">In Transit</option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ===============================================================
              TAB 8: STAFF MANAGEMENT (ADMIN ONLY)
             =============================================================== */}
          {activeTab === 'staff' && userRole === 'admin' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm h-fit">
                <h2 className="text-lg font-bold text-slate-900 mb-1">Register Clinic Staff</h2>
                <p className="text-xs text-slate-500 mb-4">
                  Creates an authenticated staff account scoped to{' '}
                  <strong>{currentUser.clinic}</strong>.
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      await apiRequest('/api/staff', 'POST', {
                        name: String(fd.get('name') || ''),
                        email: String(fd.get('email') || ''),
                        role: String(fd.get('role') || 'nurse') as RoleType,
                        phone: String(fd.get('phone') || ''),
                        password: String(fd.get('password') || ''),
                      });
                      e.currentTarget.reset();
                      notify('Staff member registered with hashed credentials');
                      await loadClinicData();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Full Name *
                    </label>
                    <input
                      name="name"
                      required
                      placeholder="Staff full name"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Email *
                    </label>
                    <input
                      name="email"
                      type="email"
                      required
                      placeholder="staff@clinic.janani.org"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">Role *</label>
                    <select
                      name="role"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    >
                      <option value="doctor">Medical Officer (Doctor)</option>
                      <option value="nurse">ANM / Staff Nurse</option>
                      <option value="field_coordinator">Field Coordinator (ASHA)</option>
                      <option value="admin">Clinic Administrator</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">Phone</label>
                    <input
                      name="phone"
                      placeholder="9000000000"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Initial Password *
                    </label>
                    <input
                      name="password"
                      type="password"
                      required
                      minLength={6}
                      placeholder="Minimum 6 characters"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-purple-700 hover:bg-purple-800 text-white font-semibold rounded-lg transition cursor-pointer"
                  >
                    Create Staff Account
                  </button>
                </form>
              </div>

              <div className="lg:col-span-8 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-slate-900 mb-4">
                  Clinic Staff Accounts ({staffList.length})
                </h2>
                <div className="divide-y divide-slate-100 text-sm">
                  {staffList.map((st) => (
                    <div key={st.id} className="py-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="font-semibold text-slate-900">{st.name}</div>
                        <div className="text-xs text-slate-500">
                          {st.email || st.id} {st.phone ? `· ${st.phone}` : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span
                          className={`text-xs px-2.5 py-0.5 rounded-full border ${
                            ROLE_BADGE_COLORS[st.normalized_role] || 'bg-slate-100'
                          }`}
                        >
                          {ROLE_LABELS[st.normalized_role] || st.role}
                        </span>
                        {st.id !== currentUser.id && (
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                await apiRequest(`/api/staff/${st.id}`, 'PATCH', {
                                  is_active: !st.is_active,
                                });
                                notify(
                                  `${st.name} ${!st.is_active ? 'activated' : 'deactivated'}`
                                );
                                await loadClinicData();
                              } catch (err: any) {
                                notify(err.message, 'error');
                              }
                            }}
                            className={`text-xs px-2.5 py-1 rounded font-semibold cursor-pointer ${
                              st.is_active
                                ? 'bg-red-50 text-red-700 hover:bg-red-100'
                                : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                            }`}
                          >
                            {st.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ===============================================================
              TAB 9: OPERATIONAL EXPENDITURE TRACKING (ADMIN ONLY)
             =============================================================== */}
          {activeTab === 'expenses' && userRole === 'admin' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm h-fit">
                <h2 className="text-lg font-bold text-slate-900 mb-1">
                  Record Programme Expenditure
                </h2>
                <p className="text-xs text-slate-500 mb-4">
                  Isolated to clinic <strong>{currentUser.clinic}</strong>. Stored in paise for
                  exact integer accounting.
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    try {
                      await apiRequest('/api/expenses', 'POST', {
                        category: String(fd.get('category') || 'transport'),
                        amount_rupees: Number(fd.get('amount_rupees')),
                        receipt_ref: String(fd.get('receipt_ref') || ''),
                        description: String(fd.get('description') || ''),
                      });
                      e.currentTarget.reset();
                      notify('Operational expense recorded');
                      await loadClinicData();
                    } catch (err: any) {
                      notify(err.message, 'error');
                    }
                  }}
                  className="space-y-3 text-sm"
                >
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Category
                    </label>
                    <select
                      name="category"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    >
                      <option value="transport">Patient Transport</option>
                      <option value="travel">Field Outreach Travel</option>
                      <option value="diagnostics">Diagnostics & Supplies</option>
                      <option value="salary">Staff Honorarium / Salary</option>
                      <option value="technology">Technology & Connectivity</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Amount (₹ Rupees) *
                    </label>
                    <input
                      name="amount_rupees"
                      type="number"
                      min={1}
                      required
                      placeholder="500"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Voucher / Receipt Reference
                    </label>
                    <input
                      name="receipt_ref"
                      placeholder="VCH-2026-042"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Description *
                    </label>
                    <textarea
                      name="description"
                      required
                      rows={2}
                      placeholder="Purpose of expenditure..."
                      className="w-full px-3 py-2 rounded-lg border border-slate-300"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg transition cursor-pointer"
                  >
                    Record Expense
                  </button>
                </form>
              </div>

              <div className="lg:col-span-8 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-slate-900 mb-4">
                  Clinic Expenditure Ledger ({expenses.length})
                </h2>
                <div className="divide-y divide-slate-100 text-sm">
                  {expenses.map((exp) => (
                    <div key={exp.id} className="py-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="font-semibold text-slate-900">
                          <span className="uppercase text-xs bg-slate-100 px-2 py-0.5 rounded mr-2">
                            {exp.category}
                          </span>
                          ₹{exp.amount_rupees.toLocaleString()}{' '}
                          <span className="text-xs text-slate-400 font-normal">
                            ({exp.amount_paise} paise)
                          </span>
                        </div>
                        <div className="text-xs text-slate-600 mt-1">
                          {exp.description}{' '}
                          {exp.receipt_ref ? `· Ref: ${exp.receipt_ref}` : ''}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await apiRequest(`/api/expenses/${exp.id}`, 'PATCH', {
                              approved: !exp.approved,
                            });
                            notify(
                              `Expense ${exp.id} ${!exp.approved ? 'approved' : 'approval revoked'}`
                            );
                            await loadClinicData();
                          } catch (err: any) {
                            notify(err.message, 'error');
                          }
                        }}
                        className={`text-xs px-3 py-1.5 rounded-lg font-semibold cursor-pointer ${
                          exp.approved
                            ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                            : 'bg-amber-100 text-amber-800 hover:bg-amber-200'
                        }`}
                      >
                        {exp.approved ? 'Approved ✓ (Click to Revoke)' : 'Pending · Click to Approve'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'expenses' && (
            <div className="mt-6">
              <FinancialAccountabilityHub
                currentUser={currentUser}
                staffList={staffList}
                notify={notify}
                onRefreshGlobal={loadClinicData}
              />
            </div>
          )}

          {/* ===============================================================
              TAB 10: ANALYTICS & AUDIT TRAIL
             =============================================================== */}
          {activeTab === 'analytics' && analytics && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                  <h3 className="font-bold text-slate-900 mb-3 text-sm uppercase tracking-wider">
                    Tasks Breakdown
                  </h3>
                  <div className="space-y-2 text-sm">
                    {Object.entries(analytics.tasks_by_status).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="capitalize text-slate-600">{k.replace('_', ' ')}</span>
                        <span className="font-bold">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                  <h3 className="font-bold text-slate-900 mb-3 text-sm uppercase tracking-wider">
                    Transport Breakdown
                  </h3>
                  <div className="space-y-2 text-sm">
                    {Object.entries(analytics.transport_by_status).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="capitalize text-slate-600">{k.replace('_', ' ')}</span>
                        <span className="font-bold">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                  <h3 className="font-bold text-slate-900 mb-3 text-sm uppercase tracking-wider">
                    Active Staff by Role
                  </h3>
                  <div className="space-y-2 text-sm">
                    {Object.entries(analytics.staff_by_role).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="capitalize text-slate-600">{k.replace('_', ' ')}</span>
                        <span className="font-bold">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {(userRole === 'admin' || userRole === 'doctor') && (
                <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
                  <h3 className="text-lg font-bold text-slate-900 mb-3">
                    Immutable Clinic Audit Trail ({events.length} recent events for{' '}
                    {currentUser.clinic})
                  </h3>
                  <div className="overflow-x-auto max-h-96">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-200 uppercase text-slate-500">
                          <th className="py-2 px-2">Timestamp</th>
                          <th className="py-2 px-2">Actor</th>
                          <th className="py-2 px-2">Action</th>
                          <th className="py-2 px-2">Entity</th>
                          <th className="py-2 px-2">Detail</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono">
                        {events.map((ev) => (
                          <tr key={ev.id} className="hover:bg-slate-50">
                            <td className="py-2 px-2 text-slate-500">
                              {new Date(ev.occurred).toLocaleString()}
                            </td>
                            <td className="py-2 px-2">
                              {ev.actor} ({ev.actor_role || 'staff'})
                            </td>
                            <td className="py-2 px-2 font-semibold text-teal-800">{ev.action}</td>
                            <td className="py-2 px-2">
                              {ev.entity}:{ev.entity_id}
                            </td>
                            <td className="py-2 px-2 text-slate-600">{ev.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===============================================================
              PHASE 5: OPERATIONS CENTRE, WORKFORCE, FIELD VISITS, PARTNERSHIPS & TRANSPORT
             =============================================================== */}
          {activeTab === 'operations' && (
            <WorkforceOperationsHub
              currentUser={currentUser}
              mothers={mothers}
              staffList={staffList}
              notify={notify}
              onRefreshGlobal={loadClinicData}
            />
          )}
        </main>
      </div>
    </div>
  );
}

