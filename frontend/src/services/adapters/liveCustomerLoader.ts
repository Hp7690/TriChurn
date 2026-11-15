export interface LiveCustomerFeatures {
  customerID: string;
  gender: 'Female' | 'Male';
  SeniorCitizen: number;
  Partner: 'Yes' | 'No';
  Dependents: 'Yes' | 'No';
  tenure: number;
  PhoneService: 'Yes' | 'No';
  MultipleLines: 'Yes' | 'No' | 'No phone service';
  InternetService: 'DSL' | 'Fiber optic' | 'No';
  OnlineSecurity: 'Yes' | 'No' | 'No internet service';
  OnlineBackup: 'Yes' | 'No' | 'No internet service';
  DeviceProtection: 'Yes' | 'No' | 'No internet service';
  TechSupport: 'Yes' | 'No' | 'No internet service';
  StreamingTV: 'Yes' | 'No' | 'No internet service';
  StreamingMovies: 'Yes' | 'No' | 'No internet service';
  Contract: 'Month-to-month' | 'One year' | 'Two year';
  PaperlessBilling: 'Yes' | 'No';
  PaymentMethod:
    | 'Bank transfer (automatic)'
    | 'Credit card (automatic)'
    | 'Electronic check'
    | 'Mailed check';
  MonthlyCharges: number;
  TotalCharges: number | null;
}

const REQUIRED_COLUMNS = [
  'customerID',
  'gender',
  'SeniorCitizen',
  'Partner',
  'Dependents',
  'tenure',
  'PhoneService',
  'MultipleLines',
  'InternetService',
  'OnlineSecurity',
  'OnlineBackup',
  'DeviceProtection',
  'TechSupport',
  'StreamingTV',
  'StreamingMovies',
  'Contract',
  'PaperlessBilling',
  'PaymentMethod',
  'MonthlyCharges',
  'TotalCharges',
] as const;

export async function loadLiveCustomers(): Promise<LiveCustomerFeatures[]> {
  const response = await fetch('/data/telco_churn_live.csv');

  if (!response.ok) {
    throw new Error(`Unable to load live customer data (${response.status}).`);
  }

  const csv = await response.text();
  if (csv.trim() === '') {
    return [];
  }
  const lines = csv.trim().split(/\r?\n/);
  const headers = lines[0].replace(/^\uFEFF/, '').split(',').map((value) =>
    value.replace(/^"|"$/g, ''),
  );
  const missingColumns = REQUIRED_COLUMNS.filter((column) => !headers.includes(column));

  if (missingColumns.length > 0) {
    throw new Error(
      `Live customer data file is not a valid customer CSV; missing required columns: ${missingColumns.join(', ')}.`,
    );
  }

  if (lines.length < 2) {
    return [];
  }

  return lines.slice(1).map((line) => {
    const values = line
      .split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/)
      .map((value) =>
        value.replace(/^"|"$/g, '').replace(/""/g, '"'),
      );

    const row = Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? '']),
    );

    return {
      customerID: row.customerID,
      gender: row.gender,
      SeniorCitizen: Number(row.SeniorCitizen),
      Partner: row.Partner,
      Dependents: row.Dependents,
      tenure: Number(row.tenure),
      PhoneService: row.PhoneService,
      MultipleLines: row.MultipleLines,
      InternetService: row.InternetService,
      OnlineSecurity: row.OnlineSecurity,
      OnlineBackup: row.OnlineBackup,
      DeviceProtection: row.DeviceProtection,
      TechSupport: row.TechSupport,
      StreamingTV: row.StreamingTV,
      StreamingMovies: row.StreamingMovies,
      Contract: row.Contract,
      PaperlessBilling: row.PaperlessBilling,
      PaymentMethod: row.PaymentMethod,
      MonthlyCharges: Number(row.MonthlyCharges),
      TotalCharges:
        String(row.TotalCharges ?? '').trim() === ''
          ? null
          : Number(row.TotalCharges),
    } as LiveCustomerFeatures;
  });
}
