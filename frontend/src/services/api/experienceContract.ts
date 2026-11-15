/** Endpoint paths for the Phase 13 experience API (all relative to the API base URL). */
export const EXPERIENCE_ENDPOINTS = {
  availability: '/api/v1/experience/availability',
  lifecycle: '/api/v1/experience/lifecycle',
  validateFeedback: '/api/v1/experience/validate-feedback',
  validateTickets: '/api/v1/experience/validate-tickets',
  validateSurvey: '/api/v1/experience/validate-survey',
  validateEvents: '/api/v1/experience/validate-events',
  dataQuality: '/api/v1/experience/data-quality',
  sentimentStatus: '/api/v1/experience/sentiment/status',
  complaintsStatus: '/api/v1/experience/complaints/status',
  npsStatus: '/api/v1/experience/nps/status',
  csatStatus: '/api/v1/experience/csat/status',
  journeyStatus: '/api/v1/experience/journey/status',
} as const;
