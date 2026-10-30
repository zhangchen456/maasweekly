# Waffo Pancake test integration

Official skill: https://docs.waffo.ai/zh/integrate/skill
SDK: @waffo/pancake-ts 0.27.0, pinned in the API service lockfile.

Scope: user-authorized test environment. Production billing remains on hold. Test records never modify paid_* ledgers or Plus entitlements. No product publishing, live payment or real refund is included.

Configured merchant MER_6hWcf71KacKLDtI1J5ukzY, store STO_5XRDhjxtHscwJdETFLbN1w, product PROD_07eKHHXHSf1IAc4Nzh6X94. Read-only SDK query confirmed an active monthly subscription at USD 9.99. Checkout uses the product price, not an amount override. The existing public planned price is not changed by this test integration.

## Configure

Set MAAS_WAFFO_TEST_ENABLED=1, WAFFO_ENVIRONMENT=test and WAFFO_PRIVATE_KEY_FILE pointing to a server-only RSA PEM file. Support also exists for WAFFO_PRIVATE_KEY or WAFFO_PRIVATE_KEY_BASE64. Keep the file outside the checkout/static roots and readable only by root and the API service. No secret belongs in Git or browser bundles.

The SDK environment option does not override the signing key's environment. Before checkout/cancellation this adapter queries merchant keys and refuses operation unless every listed key is test and the configured store/product/price match. This conservative check will block if a production key is later added; do not remove it without implementing exact signing-key environment verification.

## Endpoints

- GET /api/payment/waffo/status — administrator-only provider preflight.
- POST /api/payment/waffo/checkout — administrator + same-origin, JSON requestKey. Persist the local request before SDK submission. Reuse the same key after a timeout; refuse unknown retries older than 23 hours because provider idempotency lasts 24 hours.
- GET /api/payment/waffo/status?checkout=... — owner/admin-only receipt timeline.
- POST /api/payment/waffo/cancel — administrator + same-origin; accepts checkout ID, resolves the uniquely signed provider order ID, uses SDK cancellation. A response is not a final webhook.
- POST /api/payment/waffo/webhook — raw body, SDK test-key RSA verification and replay protection, test mode + store binding, bounded payload, durable SQLite receipt before 200. Delivery IDs deduplicate; conflicting re-deliveries fail. Unmatched valid events are retained for diagnosis. Events are evidence, not paid entitlements.
- /subscription/waffo-test/ — noindex administrator test page; same-tab hosted checkout, explicit result refresh. Browser redirects never mark payment successful.

Register an HTTP webhook on the specified store with testMode:true and URL https://daily.maas.click/api/payment/waffo/webhook. Subscribe to order.completed, subscription.activated, subscription.payment_succeeded, subscription.canceling, subscription.uncanceled, subscription.plan_changed, subscription.canceled, subscription.past_due, refund.succeeded and refund.failed. No notifications to chat/email destinations are configured.

## Validation

Full API regression 210 tests; SDK-backed signature tests include wrong store/environment, tamper, duplicate/conflicting deliveries, ownership, auth and CSRF. SSR production build passes. A real SDK preflight and sandbox checkout creation succeeded using the user-supplied key, without submitting a payment or buyer email.

Hosted payment success/decline, renewal and cancellation/refund delivery require provider sandbox execution. Do not describe checkout creation alone as end-to-end payment success. Refund initiation and automated live entitlement reconciliation remain out of scope for this isolated test adapter.
