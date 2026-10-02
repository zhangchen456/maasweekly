/** Published compatibility DTO; original Decimal strings and source condition values stay intact. */
export type SourceCondition = string | Record<string, string | number | null> | null;
export interface LedgerPrice {
  provider: string; model: string; model_display_name?: string;
  component: string; amount: string | null; amount_per_1m: string | null;
  converted_amount_per_1m?: string | null; converted_currency?: string | null;
  currency: string; unit_quantity: number; unit_name: string;
  region: string; billing_mode: string; service_tier: string;
  context_band: SourceCondition; time_condition: SourceCondition;
  observed_at: number; field_state: string; stale_reason?: string | null;
  source_url?: string | null; evidence_link?: string | null;
  modelId?: string; modelName?: string; familyId?: string; familyName?: string;
}
export interface WorkspaceData {
  prices: LedgerPrice[]; providers?: string[];
  meta: { published_at?: number; partial?: boolean; failed_sources?: string[]; artifact_version?: string };
  fx_snapshot?: { base?: string; rates?: Record<string, number>; effective_at?: number; as_of?: string };
  provider_logos?: Record<string, string>;
  modelIdentities?: { models: {modelId:string;modelName:string;familyId?:string;familyName?:string}[]; families:{familyId:string;familyName:string}[] };
}
export interface PriceVariant { key: string; label: string; rows: LedgerPrice[] }
export interface WorkspaceModel {
  key: string; provider: string; model: string; name: string;
  modelId: string | null; modelName: string | null; familyId: string | null; familyName: string | null;
  variants: Map<string, PriceVariant>; options: PriceVariant[]; variant: number;
}
