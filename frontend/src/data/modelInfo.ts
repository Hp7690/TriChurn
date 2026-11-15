import type { ChurnModelInfo, SegmentationModelInfo } from '../types';

/** Locked Phase 2 values — read-only. Do not change these numbers. */
export const LOCKED_CHURN_MODEL: ChurnModelInfo = {
  version: '2.0.0',
  artifact: 'trichurn_churn_model_v2.0.0.joblib',
  metrics: {
    rocAuc: 0.8492,
    prAuc: 0.6412,
    brierScore: 0.1355,
    logLoss: 0.4107,
    accuracy: 0.7711,
    precision: 0.5503,
    recall: 0.7429,
    f1: 0.6322,
  },
};

/** Locked Phase 5 values — read-only. */
export const LOCKED_SEGMENTATION_MODEL: SegmentationModelInfo = {
  version: '5.0.0',
  artifact: 'trichurn_segmentation_v5.0.0.joblib',
  k: 3,
  seed: 42,
  features: ['tenure', 'MonthlyCharges', 'TotalCharges', 'service_count', 'contract_risk'],
};
