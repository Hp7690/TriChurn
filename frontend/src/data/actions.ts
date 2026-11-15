import type { RetentionAction } from '../types';

/**
 * Demo retention-action catalogue used by the mock provider.
 * Costs and success rates are illustrative demo values, NOT Phase 4 outputs.
 */
export const DEMO_ACTIONS: readonly RetentionAction[] = [
  {
    id: 'contract-upgrade',
    name: 'Contract Upgrade Offer',
    description: 'Offer a discounted move from month-to-month to a longer contract.',
    cost: 230,
    successRate: 0.3,
  },
  {
    id: 'loyalty-discount',
    name: 'Loyalty Discount',
    description: 'Time-limited discount on the monthly bill for at-risk customers.',
    cost: 120,
    successRate: 0.22,
  },
  {
    id: 'service-bundle',
    name: 'Service Bundle Offer',
    description: 'Bundle additional services (e.g. security, tech support) at a reduced price.',
    cost: 65,
    successRate: 0.16,
  },
  {
    id: 'support-outreach',
    name: 'Proactive Support Call',
    description: 'Retention agent reaches out to resolve open issues before the customer leaves.',
    cost: 35,
    successRate: 0.1,
  },
];
