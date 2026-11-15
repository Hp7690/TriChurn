import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExperienceStatusBadge, STATUS_ORDER } from '../components/ExperienceStatusBadge';
import { ExperiencePage } from '../pages/ExperiencePage';
import { LifecyclePage } from '../pages/LifecyclePage';
import { ApiError } from '../services/api/errors';
import { createExperienceApi, type ExperienceApi } from '../services/experienceService';
import type { AvailabilityResponse, LifecycleResponse } from '../types/experience';
import { renderApp } from '../test/utils';
import { availability, lifecycle, moduleInfo, MODULE_KEYS } from './experienceFixtures';

function fakeApi(over: { availability?: () => Promise<AvailabilityResponse>; lifecycle?: () => Promise<LifecycleResponse> } = {}): ExperienceApi {
  return {
    baseUrl: 'http://api.test',
    getAvailability: over.availability ?? (() => Promise.resolve(availability())),
    getLifecycle: over.lifecycle ?? (() => Promise.resolve(lifecycle())),
  };
}

const renderExperience = (api: ExperienceApi) =>
  render(
    <MemoryRouter>
      <ExperiencePage api={api} />
    </MemoryRouter>,
  );

afterEach(() => vi.unstubAllGlobals());

describe('ExperienceStatusBadge', () => {
  it.each(STATUS_ORDER)('renders %s with text, not colour alone', (status) => {
    const { container } = render(<ExperienceStatusBadge status={status} />);
    expect(container.querySelector(`[data-status="${status}"]`)?.textContent?.length).toBeGreaterThan(3);
  });
});

describe('Experience Command Center', () => {
  it('shows a loading state, then all eight sections', async () => {
    renderExperience(fakeApi());
    expect(screen.queryByRole('heading', { name: /data quality summary/i })).not.toBeInTheDocument();
    for (const name of [
      /experience data availability/i, /customer lifecycle overview/i, /feedback data status/i,
      /sentiment intelligence status/i, /complaint intelligence status/i, /nps & csat availability/i,
      /customer journey availability/i, /data quality summary/i,
    ]) {
      expect(await screen.findByRole('heading', { name })).toBeInTheDocument();
    }
  });

  it('states that the page is live and not mock data', async () => {
    renderExperience(fakeApi());
    const note = await screen.findByRole('note');
    expect(note).toHaveTextContent('http://api.test');
    expect(note).toHaveTextContent(/nothing on this page is mock data/i);
  });

  it('shows counts per status from the API summary', async () => {
    renderExperience(fakeApi());
    const blocked = await screen.findByRole('region', { name: 'Blocked by missing data' });
    expect(within(blocked).getByText('6')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Available' })).getByText('1')).toBeInTheDocument();
  });

  it('blocked modules explain exactly what data activates them and show no figures', async () => {
    renderExperience(fakeApi());
    const card = await screen.findByRole('article', { name: 'nps title' });
    expect(within(card).getByText('Blocked by missing data')).toBeInTheDocument();
    expect(within(card).getByText(/what is needed to activate/i)).toBeInTheDocument();
    expect(within(card).getByText(/NPS survey responses with response_id/)).toBeInTheDocument();
    expect(within(card).getByText('nps_id')).toBeInTheDocument();
    expect(within(card).queryByRole('definition')).not.toBeInTheDocument();
  });

  it('available modules show API metrics and a low-sample warning', async () => {
    const api = fakeApi({
      availability: () =>
        Promise.resolve(
          availability({
            modules: MODULE_KEYS.map((k) =>
              k === 'nps'
                ? moduleInfo('nps', {
                    status: 'AVAILABLE', reason: null, dataset_configured: true,
                    metrics: { value: 25, valid_responses: 4, low_sample: true },
                    validation: { rows_total: 4, rows_valid: 4, error_count: 0, warning_count: 0, valid: true },
                  })
                : moduleInfo(k),
            ),
          }),
        ),
    });
    renderExperience(api);
    const card = await screen.findByRole('article', { name: 'nps title' });
    expect(within(card).getByText('NPS')).toBeInTheDocument();
    expect(within(card).getByText('25')).toBeInTheDocument();
    expect(within(card).getByText(/low sample/i)).toBeInTheDocument();
    expect(within(card).getByText(/4 of 4 rows valid/)).toBeInTheDocument();
    expect(within(card).queryByText(/what is needed to activate/i)).not.toBeInTheDocument();
  });

  it('renders every distinct status', async () => {
    const statuses = ['PARTIALLY_AVAILABLE', 'DISABLED', 'VALIDATION_FAILED'] as const;
    const modules = MODULE_KEYS.map((k, i) => (i >= 1 && i <= 3 ? moduleInfo(k, { status: statuses[i - 1] }) : moduleInfo(k)));
    const { container } = renderExperience(fakeApi({ availability: () => Promise.resolve(availability({ modules })) }));
    await screen.findByRole('heading', { name: /data quality summary/i });
    for (const s of statuses) expect(container.querySelector(`article [data-status="${s}"]`)).not.toBeNull();
  });

  it('shows the lifecycle overview as a labelled tenure proxy with a link', async () => {
    renderExperience(fakeApi());
    expect(await screen.findByText(/120 customers by tenure group/i)).toBeInTheDocument();
    expect(screen.getByText(/not an event-based customer journey/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open lifecycle analysis/i })).toHaveAttribute('href', '/experience-lifecycle');
    expect(screen.getByRole('img', { name: /Customers per tenure lifecycle group/ })).toBeInTheDocument();
  });

  it('shows an empty state instead of a chart when lifecycle is unavailable', async () => {
    const modules = MODULE_KEYS.map((k) =>
      k === 'lifecycle' ? moduleInfo('lifecycle', { status: 'BLOCKED_BY_MISSING_DATA', reason: 'The customer dataset file was not found.' }) : moduleInfo(k));
    renderExperience(fakeApi({ availability: () => Promise.resolve(availability({ modules, lifecycle_summary: null })) }));
    expect(await screen.findByText('Lifecycle overview unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /tenure lifecycle group/i })).not.toBeInTheDocument();
  });

  it('data quality shows configured dataset validation and "not configured" otherwise', async () => {
    const dq = availability().data_quality;
    renderExperience(fakeApi({ availability: () => Promise.resolve(availability({
      data_quality: { ...dq, datasets: { ...dq.datasets, tickets: { rows_total: 10, rows_valid: 9, error_count: 1, warning_count: 2, valid: false } } },
    })) }));
    expect(await screen.findByText('customers.csv')).toBeInTheDocument();
    expect(screen.getAllByText(/not configured: nothing to validate/i)).toHaveLength(4);
    const row = screen.getByRole('row', { name: /tickets/i });
    expect(within(row).getByText('9')).toBeInTheDocument();
  });

  it('shows a configuration error alert', async () => {
    renderExperience(fakeApi({ availability: () => Promise.resolve(availability({ config_error: 'limits.max_bytes must be >= 1.' })) }));
    expect(await screen.findByText(/limits\.max_bytes must be >= 1\./)).toBeInTheDocument();
  });

  it('shows an error state with retry, and recovers', async () => {
    const getAvailability = vi.fn().mockRejectedValueOnce(new ApiError('The experience API could not be reached.')).mockResolvedValue(availability());
    renderExperience(fakeApi({ availability: getAvailability }));
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be reached');
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByRole('heading', { name: /data quality summary/i })).toBeInTheDocument();
    expect(getAvailability).toHaveBeenCalledTimes(2);
  });
});

describe('Lifecycle page', () => {
  const renderLifecycle = (api: ExperienceApi) => render(<MemoryRouter><LifecyclePage api={api} /></MemoryRouter>);

  it('labels itself a tenure proxy, never a journey', async () => {
    renderLifecycle(fakeApi());
    expect(await screen.findByText('TENURE PROXY')).toBeInTheDocument();
    expect(screen.getAllByText(/not an event-based customer journey/i).length).toBeGreaterThan(0);
  });

  it('renders KPI cards from the API', async () => {
    renderLifecycle(fakeApi());
    const analysed = await screen.findByRole('region', { name: 'Customers analysed' });
    expect(within(analysed).getByText('118')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Observed churn rate' })).getByText('10.17%')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Excluded rows' })).getByText('2')).toBeInTheDocument();
  });

  it('renders the group table, withholding small-group churn rates', async () => {
    renderLifecycle(fakeApi());
    const table = await screen.findByRole('table', { name: 'Lifecycle group statistics' });
    const newRow = within(table).getByRole('row', { name: /New Customer/ });
    expect(within(newRow).getByText('0–5 months')).toBeInTheDocument();
    expect(within(newRow).getByText('40%')).toBeInTheDocument();
    const longRow = within(table).getByRole('row', { name: /Long-Term Customer/ });
    expect(within(longRow).getByText('6+ months')).toBeInTheDocument();
    expect(within(longRow).getByText('Withheld')).toHaveAttribute('title', 'Fewer than 50 labelled customers in this group.');
  });

  it('shows a blocked risk card instead of invented risk figures', async () => {
    renderLifecycle(fakeApi());
    const card = await screen.findByText('Lifecycle risk distribution');
    const region = card.closest('section') ?? card.parentElement!;
    expect(within(region).getByText('Blocked by missing data')).toBeInTheDocument();
    expect(screen.getByText(/never re-predicted or estimated/i)).toBeInTheDocument();
  });

  it('shows risk bands when existing probabilities are available', async () => {
    renderLifecycle(fakeApi({ lifecycle: () => Promise.resolve(lifecycle({ risk_distribution: {
      status: 'AVAILABLE', bands: { LOW: 5, MEDIUM: 3, HIGH: 2 }, missing_probability: 1, source: "dataset column 'churn_probability'", note: 'Bands use policy thresholds.' } })) }));
    expect(await screen.findByText('LOW risk')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/Customers without a valid probability: 1/)).toBeInTheDocument();
  });

  it('charts handle empty data (every churn rate withheld)', async () => {
    const withheld = lifecycle();
    withheld.groups = withheld.groups.map((g) => ({ ...g, churn: g.churn && { ...g.churn, churn_rate_pct: null } }));
    renderLifecycle(fakeApi({ lifecycle: () => Promise.resolve(withheld) }));
    await screen.findByText('Observed churn rate by group');
    expect(screen.getByText('No chart data')).toBeInTheDocument();
  });

  it.each([
    ['BLOCKED_BY_MISSING_DATA', 'The customer dataset file was not found.'],
    ['DISABLED', 'The lifecycle module is disabled in configs/experience.yaml.'],
    ['VALIDATION_FAILED', 'Required column(s) missing from the customer dataset: tenure.'],
  ] as const)('shows an empty state for %s', async (status, reason) => {
    renderLifecycle(fakeApi({ lifecycle: () => Promise.resolve(lifecycle({ status, reason, customers_analysed: 0, groups: [], overall: null, risk_distribution: null })) }));
    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows an error state and retries', async () => {
    const getLifecycle = vi.fn().mockRejectedValueOnce(new ApiError('boom')).mockResolvedValue(lifecycle());
    renderLifecycle(fakeApi({ lifecycle: getLifecycle }));
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('TENURE PROXY')).toBeInTheDocument();
  });
});

describe('experience API client', () => {
  const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

  it('calls the experience endpoints on the configured base URL', async () => {
    const fetchImpl = vi.fn().mockImplementation(() => ok({ ok: true }));
    const api = createExperienceApi({ baseUrl: 'http://x.test///', fetchImpl });
    expect(api.baseUrl).toBe('http://x.test');
    await api.getAvailability();
    await api.getLifecycle();
    expect(fetchImpl.mock.calls.map((c) => c[0])).toEqual([
      'http://x.test/api/v1/experience/availability', 'http://x.test/api/v1/experience/lifecycle']);
  });

  it('surfaces the API error envelope message and status', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'CAPABILITY_UNAVAILABLE', message: 'Experience module unavailable.' } }), { status: 503 }));
    const err = await createExperienceApi({ baseUrl: 'http://x.test', fetchImpl }).getAvailability().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe('Experience module unavailable.');
  });

  it('falls back to a generic message for non-JSON errors and network failures', async () => {
    const generic = await createExperienceApi({ baseUrl: 'http://x.test', fetchImpl: vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })) }).getLifecycle().catch((e: unknown) => e);
    expect((generic as Error).message).toContain('502');
    const down = await createExperienceApi({ baseUrl: 'http://x.test', fetchImpl: vi.fn().mockRejectedValue(new TypeError('failed')) }).getLifecycle().catch((e: unknown) => e);
    expect((down as Error).message).toContain('could not be reached');
  });
});

describe('navigation regression', () => {
  it('keeps every existing sidebar entry and adds the two experience entries', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(availability()), { status: 200 }))));
    renderApp('/dashboard');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent?.trim());
    expect(labels).toEqual(['Dashboard', 'Customers', 'Segments', 'Insights', 'What-if', 'Retention', 'Autonomous', 'Revenue', 'Model', 'Experience', 'Lifecycle', 'Settings']);
    expect(within(nav).getByRole('link', { name: 'Customers' })).toHaveAttribute('href', '/customers');
    expect(within(nav).getByRole('link', { name: 'Experience' })).toHaveAttribute('href', '/experience');
    expect(within(nav).getByRole('link', { name: 'Lifecycle' })).toHaveAttribute('href', '/experience-lifecycle');
  });

  it('serves the experience routes inside the app layout without breaking existing routes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(
      JSON.stringify(String(url).endsWith('/lifecycle') ? lifecycle() : availability()), { status: 200 }))));
    const { unmount } = renderApp('/experience');
    expect(await screen.findByRole('heading', { name: 'Experience Command Center' })).toBeInTheDocument();
    unmount();
    const second = renderApp('/experience-lifecycle');
    expect(await screen.findByText('TENURE PROXY')).toBeInTheDocument();
    second.unmount();
    renderApp('/customers');
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument());
    expect(screen.queryByText('TENURE PROXY')).not.toBeInTheDocument();
  });
});
