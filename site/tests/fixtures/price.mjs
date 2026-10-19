// Stable quote for selection tests; never borrow a live provider's current evidence.
export const priceFixture = {
 id:'fixture-input', providerId:'alibaba', sourceId:'alibaba-pricing', modelKey:'fixture',
 modelId:'alibaba:fixture', component:'input', amount:'2', currency:'CNY',
 unitName:'token', unitQuantity:1000000, region:'cn', billingMode:'realtime',
 serviceTier:'standard', contextBand:null, timeCondition:null,
 observedAt:'2026-10-01T00:00:00Z', quality:{state:'fresh'}, evidenceStatus:'complete',
};
