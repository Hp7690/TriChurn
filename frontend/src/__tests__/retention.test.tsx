import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { NotFoundError } from '../services/api/errors';
import { apiDown, FakeRetentionProvider, SUMMARY } from '../test/fakeRetention';
import { renderRetention } from '../test/retentionUtils';
import { formatMoney, formatRatio } from '../utils/money';

describe('Retention overview', () => {
  it('shows estimate-labelled KPIs, charts, campaign summary and top priorities', async () => {
    renderRetention('/retention');
    expect(await screen.findByText('Revenue at Risk')).toBeInTheDocument();
    ['Intervention Candidates', 'High-Priority Customers', 'Estimated Campaign Cost', 'Estimated Retained Revenue', 'Estimated Net Benefit'].forEach((label) =>
      expect(screen.getByText(label)).toBeInTheDocument(),
    );
    expect(screen.getByRole('note')).toHaveTextContent(/not measured results/i);
    expect(screen.getByText('Top Retention Priorities')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'C-001' })).toHaveAttribute('href', '/retention/recommendations/C-001');
  });

  it('formats money in the Phase 4 currency (INR)', () => {
    expect(formatMoney(1234567, 'INR')).toContain('₹');
    expect(formatRatio(null)).toBe('—');
    expect(formatRatio(0.5)).toBe('50%');
  });

  it('shows an empty state for an empty portfolio', async () => {
    const provider = new FakeRetentionProvider();
    provider.summary = { ...SUMMARY, total_customers: 0 };
    renderRetention('/retention', provider);
    expect(await screen.findByText('No scored customers')).toBeInTheDocument();
  });

  it('shows an error with Retry and recovers', async () => {
    const provider = new FakeRetentionProvider();
    provider.failWith = apiDown();
    renderRetention('/retention', provider);
    expect(await screen.findByText('Unable to load the retention summary.')).toBeInTheDocument();
    provider.failWith = null;
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Revenue at Risk')).toBeInTheDocument();
  });
});

describe('Retention priorities', () => {
  it('lists ranked customers with tiers and expandable reasons', async () => {
    renderRetention('/retention/priorities');
    const table = await screen.findByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(4);
    expect(within(table).getByText('Monitor')).toBeInTheDocument();
    expect(screen.getAllByText('Reasons').length).toBe(3);
    expect(screen.getByText(/not a probability/i)).toBeInTheDocument();
  });

  it('sends filters to the service and resets to page 1', async () => {
    const { provider } = renderRetention('/retention/priorities');
    await screen.findByRole('table');
    await userEvent.selectOptions(screen.getByLabelText('Priority tier'), 'P1');
    await waitFor(() => expect(provider.lastPriorityQuery?.tier).toBe('P1'));
    expect(provider.lastPriorityQuery?.page).toBe(1);
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2));
  });

  it('shows an empty state when nothing matches', async () => {
    const { provider } = renderRetention('/retention/priorities');
    await screen.findByRole('table');
    await userEvent.selectOptions(screen.getByLabelText('Priority tier'), 'P4');
    expect(await screen.findByText('No customers match these filters')).toBeInTheDocument();
    expect(provider.lastPriorityQuery?.tier).toBe('P4');
  });
});

describe('Retention recommendations', () => {
  it('asks for a customer when none is given', async () => {
    renderRetention('/retention/recommendations');
    expect(await screen.findByLabelText('Customer ID')).toBeInTheDocument();
  });

  it('shows the decision, reasons, comparison and SHAP drivers with their caveat', async () => {
    renderRetention('/retention/recommendations/C-001');
    expect(await screen.findByText('Recommendation for C-001')).toBeInTheDocument();
    expect(screen.getByText(/Phase 4 says intervene/)).toBeInTheDocument();
    expect(screen.getByText(/receive Discount offer/)).toBeInTheDocument();
    expect(screen.getByText('Contract = Month-to-month')).toBeInTheDocument();
    expect(screen.getByText(/describe the model, not causes/)).toBeInTheDocument();
    expect(screen.getByText(/Causal claim: no/)).toBeInTheDocument();
  });

  it('degrades gracefully when explainability is unavailable', async () => {
    renderRetention('/retention/recommendations/C-002');
    expect(await screen.findByText('Recommendation for C-002')).toBeInTheDocument();
    expect(screen.getByText(/Explainability is not available right now/)).toBeInTheDocument();
  });

  it('shows not-found for an unknown customer', async () => {
    renderRetention('/retention/recommendations/NOPE');
    expect(await screen.findByText('Customer not found')).toBeInTheDocument();
  });

  it('shows a retryable error for other failures', async () => {
    const provider = new FakeRetentionProvider();
    provider.failWith = apiDown();
    renderRetention('/retention/recommendations/C-001', provider);
    expect(await screen.findByText('Unable to load the recommendation.')).toBeInTheDocument();
    expect(NotFoundError).toBeDefined();
  });
});

describe('Retention simulator', () => {
  it('runs a scenario and labels every result as an estimate', async () => {
    const { provider } = renderRetention('/retention/simulator');
    await userEvent.click(await screen.findByRole('button', { name: 'Run simulation' }));
    expect(await screen.findByText('Results (estimates)')).toBeInTheDocument();
    expect(provider.lastScenarios).toHaveLength(1);
    expect(provider.lastScenarios[0].successRateOverride).toBeUndefined();
    expect(screen.getByText('best net benefit')).toBeInTheDocument();
  });

  it('sends overrides as fractions and supports comparing scenarios', async () => {
    const { provider } = renderRetention('/retention/simulator');
    await screen.findByRole('button', { name: 'Run simulation' });
    await userEvent.type(screen.getByLabelText('Success rate % (override)'), '40');
    await userEvent.click(screen.getByRole('button', { name: 'Add scenario' }));
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }));
    await screen.findByText('Results (estimates)');
    expect(provider.lastScenarios).toHaveLength(2);
    expect(provider.lastScenarios[0].successRateOverride).toBeCloseTo(0.4);
  });

  it('blocks invalid input before calling the service', async () => {
    const { provider } = renderRetention('/retention/simulator');
    await screen.findByRole('button', { name: 'Run simulation' });
    fireEvent.change(screen.getByLabelText('Success rate % (override)'), { target: { value: '150' } });
    expect(screen.getByRole('alert')).toHaveTextContent(/between 0 and 100/);
    expect(screen.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
    expect(provider.calls).not.toContain('simulate');
  });

  it('stops adding scenarios at the limit and shows service errors', async () => {
    const provider = new FakeRetentionProvider();
    renderRetention('/retention/simulator', provider);
    await screen.findByRole('button', { name: 'Run simulation' });
    for (let i = 0; i < 5; i += 1) {
      const add = screen.getByRole('button', { name: 'Add scenario' });
      if (!(add as HTMLButtonElement).disabled) await userEvent.click(add);
    }
    expect(screen.getByRole('button', { name: 'Add scenario' })).toBeDisabled();
    provider.failWith = apiDown();
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }));
    expect(await screen.findByText('Unable to run the simulation.')).toBeInTheDocument();
  });
});

describe('Retention campaigns', () => {
  it('starts empty: no fabricated campaigns, and readiness says NOT READY', async () => {
    renderRetention('/retention/campaigns');
    expect(await screen.findByText('No campaigns recorded yet')).toBeInTheDocument();
    expect(await screen.findByText(/NOT READY/)).toBeInTheDocument();
    expect(screen.getByText(/No uplift model exists/)).toBeInTheDocument();
  });

  it('creates a campaign through the service and then lists it with separate estimated and actual columns', async () => {
    const { provider } = renderRetention('/retention/campaigns');
    await screen.findByText('No campaigns recorded yet');
    await userEvent.type(screen.getByLabelText('Name'), 'Spring win-back');
    fireEvent.change(screen.getByLabelText('Campaign date'), { target: { value: '2025-03-01' } });
    await userEvent.click(screen.getByRole('button', { name: 'Create campaign' }));
    expect(await screen.findByText(/Campaign cmp_test0001 created/)).toBeInTheDocument();
    expect(provider.calls).toContain('createCampaign');
    expect(await screen.findByText('Spring win-back')).toBeInTheDocument();
    expect(screen.getAllByText('ESTIMATE').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Recorded').length).toBeGreaterThan(0);
  });

  it('assigns customers and reports the outcome', async () => {
    renderRetention('/retention/campaigns');
    await screen.findByText('No campaigns recorded yet');
    await userEvent.type(screen.getByLabelText('Campaign ID', { selector: '#as-campaign' }), 'cmp_test0001');
    await userEvent.type(screen.getByLabelText(/Customer IDs/), 'C-001, C-002 C-001');
    await userEvent.click(screen.getByRole('button', { name: 'Assign customers' }));
    expect(await screen.findByText(/Assigned 2 of 2/)).toBeInTheDocument();
  });

  it('shows API failures from recording as an alert', async () => {
    const provider = new FakeRetentionProvider();
    renderRetention('/retention/campaigns', provider);
    await screen.findByText('No campaigns recorded yet');
    provider.failWith = new NotFoundError('Campaign not found.');
    await userEvent.type(screen.getByLabelText('Campaign ID', { selector: '#oc-campaign' }), 'cmp_missing');
    await userEvent.type(screen.getByLabelText('Customer ID', { selector: '#oc-customer' }), 'C-001');
    await userEvent.click(screen.getByRole('button', { name: 'Record outcome' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Campaign not found.');
  });
});
