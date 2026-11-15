import { Activity, CheckCircle2, ClipboardList, Hourglass, ShieldAlert, Wallet } from 'lucide-react';
import { useState } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { KpiCard } from '../../components/KpiCard';
import { Notice } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { useAutonomy } from '../../services/autonomy';
import { formatMoney } from '../../utils/money';

export function CommandCenterPage() {
  const service = useAutonomy();
  const [version, setVersion] = useState(0);
  const state = useAsync(() => service.getSummary(), [service, version]);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (work: () => Promise<string>) => {
    setBusy(true);
    try {
      setMessage({ tone: 'ok', text: await work() });
      setVersion((v) => v + 1);
    } catch (e) {
      setMessage({ tone: 'error', text: toError(e).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AsyncBoundary state={state} errorTitle="Unable to load the autonomous retention summary.">
      {(s) => {
        const st = s.status;
        const byStatus = s.recommendations.status;
        return (
          <div className="space-y-6">
            {!st.approvals_available && (
              <Notice tone="warn">
                Approvals are disabled: {st.identity_provider_configured ? 'the approval workflow is switched off in configuration.' : 'no identity provider is configured for this API, so nobody can be an authorised reviewer.'} Recommendations can be generated and reviewed, but not approved, rejected or executed.
              </Notice>
            )}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <KpiCard label="Pending Recommendations" value={String(byStatus.pending ?? 0)} icon={Hourglass} tone="brand" />
              <KpiCard label="Approved / Executed" value={`${byStatus.approved ?? 0} / ${byStatus.executed ?? 0}`} icon={CheckCircle2} tone="success" />
              <KpiCard label="Open Risk Events" value={String(Object.values(s.open_risk_events).reduce((a, b) => a + b, 0))} hint={st.monitoring_mode} icon={ShieldAlert} tone="danger" />
              <KpiCard label="Observed Outcomes" value={String(s.observed.validated_outcomes)} hint="Recorded results only" icon={ClipboardList} />
              <KpiCard label="Estimated Net Benefit (pending)" value={formatMoney(s.estimated.estimated_net_benefit_pending)} hint="ESTIMATE · assumed success rates, not saved revenue" icon={Wallet} />
              <KpiCard label="Rules Version" value={st.rules_version} hint="Deterministic rules, no LLM" icon={Activity} />
            </div>

            <Card title="Capabilities" description="What is switched on in this deployment">
              <ul className="grid gap-2 text-sm sm:grid-cols-2">
                <li>Agent: <strong>{st.agent_enabled ? 'enabled' : 'disabled'}</strong> (rule-based)</li>
                <li>Risk monitoring: <strong>{st.monitoring_enabled ? 'enabled' : 'disabled'}</strong> ({st.monitoring_mode})</li>
                <li>Approvals: <strong>{st.approvals_available ? 'available' : 'disabled'}</strong></li>
                <li>Learning: <strong>{st.learning_enabled ? 'enabled' : 'not enabled'}</strong> (no model is retrained)</li>
                <li className="sm:col-span-2">Execution: {st.execution_integration}</li>
              </ul>
            </Card>

            <Card title="Actions" description="Non-consequential: these create internal records only.">
              {message && <div className="mb-3"><Notice tone={message.tone}>{message.text}</Notice></div>}
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={busy || !st.agent_enabled} onClick={() => void run(async () => {
                  const r = await service.generateRecommendations(500);
                  return `Evaluated ${r.considered} customers: ${r.created} new recommendations, ${r.skipped_existing} already existed.`;
                })} className="btn btn-primary">
                  Generate recommendations
                </button>
                <button type="button" disabled={busy || !st.monitoring_enabled} onClick={() => void run(async () => {
                  const r = await service.scanRisks();
                  return `Scan ${r.status}: ${r.events_created} new events, ${r.events_resolved} resolved. ${r.note}`;
                })} className="btn btn-secondary">
                  Run batch risk scan
                </button>
              </div>
              <p className="mt-3 text-xs text-slate-500">{s.estimated.note}</p>
            </Card>
          </div>
        );
      }}
    </AsyncBoundary>
  );
}
