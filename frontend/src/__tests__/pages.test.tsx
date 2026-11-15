import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MOCK_CUSTOMER_COUNT, MOCK_INTELLIGENCE } from '../data/mockDataset';
import { createTestService, renderApp } from '../test/utils';

describe('pages', () => {
  it('dashboard loads KPIs, charts and the recent high-risk table, and is labelled as demo data', async () => {
    renderApp('/dashboard');
    expect(await screen.findByText('Total Customers')).toBeInTheDocument();
    [
      'High Risk Customers',
      'Avg Churn Probability',
      'Value at Risk (VaR)',
      'Retention Opportunities',
      'Expected Net Benefit',
    ].forEach((label) => expect(screen.getByText(label)).toBeInTheDocument());
    const total = screen.getByRole('region', { name: 'Total Customers' });
    expect(within(total).getByText(String(MOCK_CUSTOMER_COUNT))).toBeInTheDocument();
    expect(screen.getByText('Churn Risk Distribution')).toBeInTheDocument();
    expect(screen.getByText('Recent High-Risk Customers')).toBeInTheDocument();
    expect(screen.getByText(/DEMO DATA/)).toBeInTheDocument();
  });

  it('customers page lists customers and filters by search', async () => {
    renderApp('/customers');
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(11);

    await userEvent.type(screen.getByLabelText('Search customer ID'), 'TC-1005');
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2));
    expect(screen.getByRole('button', { name: 'TC-1005' })).toBeInTheDocument();
  });

  it('customers page shows an empty state for filters that match nothing', async () => {
    renderApp('/customers?q=ZZZ');
    expect(await screen.findByText('No customers match these filters')).toBeInTheDocument();
  });

  it('selecting a customer opens its detail page', async () => {
    renderApp('/customers');
    const table = await screen.findByRole('table');
    const first = within(table).getAllByRole('button', { name: /^TC-\d{4}$/ })[0];
    const id = first.textContent ?? '';
    await userEvent.click(first);
    expect(await screen.findByRole('heading', { name: id })).toBeInTheDocument();
  });

  it('customer detail shows overview, business value and explainability', async () => {
    renderApp('/customers/TC-1001');
    expect(await screen.findByRole('heading', { name: 'TC-1001' })).toBeInTheDocument();
    expect(screen.getByText('Customer Overview')).toBeInTheDocument();
    expect(screen.getByText('Business Value')).toBeInTheDocument();
    expect(screen.getByText('Explainability')).toBeInTheDocument();
    expect(screen.getByText(/Top churn drivers/)).toBeInTheDocument();
  });

  it('customer detail handles an invalid customer without a blank screen', async () => {
    renderApp('/customers/TC-9999');
    expect(await screen.findByText('Customer not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to customers' })).toBeInTheDocument();
  });

  it('segments page shows the three locked segments and reveals customers on click', async () => {
    renderApp('/segments');
    expect((await screen.findAllByText('Low Value / High Risk')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('High Value / Stable').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Low Value / Stable').length).toBeGreaterThan(0);

    await userEvent.click(screen.getAllByRole('button', { name: /Low Value \/ High Risk/ })[0]);
    expect(await screen.findByText('Customers in Low Value / High Risk')).toBeInTheDocument();
    expect(await screen.findAllByRole('table')).not.toHaveLength(0);
  });

  it('insights page shows rankings and the action summary', async () => {
    renderApp('/insights');
    expect(await screen.findByText('Highest-VaR customers')).toBeInTheDocument();
    expect(screen.getByText('Highest-value customers at risk')).toBeInTheDocument();
    expect(screen.getByText('Highest-ENB opportunities')).toBeInTheDocument();
    expect(screen.getByText('Action Summary')).toBeInTheDocument();
    ['Customers', 'Average Cost', 'Success Rate', 'Expected Benefit'].forEach((h) =>
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument(),
    );
  });

  it('what-if page loads, labels itself as a scenario and runs a scenario', async () => {
    const dataset = MOCK_INTELLIGENCE.map((item) =>
      item.customer.customerId === 'TC-1001'
        ? { ...item, business: { ...item.business, clv: 1195.8000000000002 } }
        : item,
    );
    renderApp('/what-if', createTestService({ dataset }));
    expect(await screen.findAllByText('Scenario / What-if analysis')).not.toHaveLength(0);
    expect(await screen.findByText('New ENB')).toBeInTheDocument();
    expect(screen.getByText('Current State')).toBeInTheDocument();

    const clvInput = screen.getByLabelText(/CLV scenario/);
    expect(clvInput).toHaveAttribute('step', 'any');
    expect(clvInput).toBeValid();
    fireEvent.change(screen.getByLabelText(/Churn probability scenario/), { target: { value: '90' } });
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }));
    expect(await screen.findByText('90.0%')).toBeInTheDocument();
  });

  it('model page shows the locked Phase 2 metrics and Phase 5 configuration', async () => {
    renderApp('/model');
    for (const value of ['0.8492', '0.6412', '0.1355', '0.4107', '0.7711', '0.5503', '0.7429', '0.6322']) {
      expect(await screen.findByText(value)).toBeInTheDocument();
    }
    expect(await screen.findByText('K (segments)')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('service_count')).toBeInTheDocument();
  });

  it('shows an unknown-route page', async () => {
    renderApp('/nope');
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });

  it('shows an error state with Retry when the data source fails, then recovers', async () => {
    const service = createTestService({ failureMode: 'always' });
    renderApp('/dashboard', service);
    expect(await screen.findByText('Unable to load customer intelligence.')).toBeInTheDocument();

    service.setSimulatedFailure(false);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Total Customers')).toBeInTheDocument();
  });

  it('settings page can toggle simulated failure', async () => {
    renderApp('/settings');
    const toggle = await screen.findByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });
});
