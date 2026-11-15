import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Users } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import { CustomerFilters, DEFAULT_CUSTOMER_FILTERS } from '../components/CustomerFilters';
import { CustomerTable } from '../components/CustomerTable';
import { DecisionBadge } from '../components/DecisionBadge';
import { EmptyState } from '../components/EmptyState';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { ErrorState } from '../components/ErrorState';
import { KpiCard } from '../components/KpiCard';
import { RiskBadge } from '../components/RiskBadge';
import { SegmentBadge } from '../components/SegmentBadge';
import { MOCK_INTELLIGENCE } from '../data/mockDataset';

describe('KpiCard', () => {
  it('renders label, value and hint', () => {
    render(<KpiCard label="Total Customers" value="80" hint="demo" icon={Users} />);
    const card = screen.getByRole('region', { name: 'Total Customers' });
    expect(within(card).getByText('80')).toBeInTheDocument();
    expect(within(card).getByText('demo')).toBeInTheDocument();
  });
});

describe('badges', () => {
  it.each(['Low', 'Medium', 'High'] as const)('RiskBadge renders %s', (band) => {
    render(<RiskBadge band={band} />);
    expect(screen.getByText(band)).toBeInTheDocument();
  });

  it('SegmentBadge and DecisionBadge render their labels', () => {
    render(
      <>
        <SegmentBadge segmentId="high-value-stable" label="High Value / Stable" />
        <DecisionBadge decision="Intervene" />
      </>,
    );
    expect(screen.getByText('High Value / Stable')).toBeInTheDocument();
    expect(screen.getByText('Intervene')).toBeInTheDocument();
  });
});

describe('CustomerTable', () => {
  const rows = MOCK_INTELLIGENCE.slice(0, 3);

  it('renders one row per customer plus the header, with all required columns', () => {
    render(<CustomerTable rows={rows} onSelect={() => undefined} />);
    expect(screen.getAllByRole('row')).toHaveLength(rows.length + 1);
    ['Customer ID', 'Churn Probability', 'Risk Band', 'Segment', 'CLV', 'VaR', 'ENB', 'Recommended Action', 'Decision'].forEach((h) =>
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument(),
    );
    rows.forEach((r) => expect(screen.getByRole('button', { name: r.prediction.customerId })).toBeInTheDocument());
  });

  it('calls onSelect when a customer is chosen by button or row', async () => {
    const onSelect = vi.fn();
    render(<CustomerTable rows={rows} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('button', { name: rows[0].prediction.customerId }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(rows[0].prediction.customerId);
    await userEvent.click(within(screen.getAllByRole('row')[2]).getByText(rows[1].business.decision));
    expect(onSelect).toHaveBeenLastCalledWith(rows[1].prediction.customerId);
  });

  it('makes sortable headers interactive only when onSort is provided', async () => {
    const onSort = vi.fn();
    const { rerender } = render(<CustomerTable rows={rows} onSelect={() => undefined} />);
    expect(screen.queryByRole('button', { name: 'CLV' })).not.toBeInTheDocument();
    rerender(<CustomerTable rows={rows} onSelect={() => undefined} onSort={onSort} sortKey="clv" sortDirection="asc" />);
    expect(screen.getByRole('columnheader', { name: 'CLV' })).toHaveAttribute('aria-sort', 'ascending');
    await userEvent.click(screen.getByRole('button', { name: 'VaR' }));
    expect(onSort).toHaveBeenCalledWith('valueAtRisk');
  });
});

describe('CustomerFilters', () => {
  it('reports filter, search and sort changes', async () => {
    const onChange = vi.fn();
    render(<CustomerFilters value={DEFAULT_CUSTOMER_FILTERS} onChange={onChange} />);

    await userEvent.selectOptions(screen.getByLabelText('Risk band'), 'High');
    expect(onChange).toHaveBeenLastCalledWith({ risk: 'High' });

    await userEvent.selectOptions(screen.getByLabelText('Segment'), 'high-value-stable');
    expect(onChange).toHaveBeenLastCalledWith({ segment: 'high-value-stable' });

    await userEvent.selectOptions(screen.getByLabelText('Churn probability'), '0.5');
    expect(onChange).toHaveBeenLastCalledWith({ minProbability: 0.5 });

    await userEvent.type(screen.getByLabelText('Search customer ID'), 'T');
    expect(onChange).toHaveBeenLastCalledWith({ search: 'T' });

    await userEvent.click(screen.getByRole('button', { name: /toggle sort direction/i }));
    expect(onChange).toHaveBeenLastCalledWith({ sortDirection: 'asc' });
  });
});

describe('state components', () => {
  it('ErrorState shows the message and a working Retry button', async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="boom" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load customer intelligence.');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('EmptyState renders title and description', () => {
    render(<EmptyState title="Nothing here" description="Try again later" />);
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    expect(screen.getByText('Try again later')).toBeInTheDocument();
  });

  it('ErrorBoundary renders a fallback instead of a blank screen', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error('render failure');
    }
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    spy.mockRestore();
  });
});
