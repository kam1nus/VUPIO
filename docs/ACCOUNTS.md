# Account and membership foundation

Account sign-in is optional. Existing soundboard, Discover, Radar, Studio, audio routing and remote features are available without sign-in. This release takes no payments and does not enforce paid feature limits.

## Connect a computer

1. In VUPIO, open **Account → Sign in**.
2. Choose **Continue on website**, sign in with ChatGPT and compare the displayed code with the app.
3. Approve only a sign-in you started for a computer you recognize.
4. Return to VUPIO. Sign-in completes automatically. Codes expire after 10 minutes and are single-use.
5. Manage devices on the website's **My account** page or in the app. Disconnecting a device immediately invalidates its server session. The desktop notices on Refresh or the next account operation; it does not block the soundboard.

The website uses its existing Sites ChatGPT identity. Email/password sign-in is not included. The server's D1 database stores the account ID, display name/email, computer name/platform, session expiration/revocation and membership status. It does not receive your sound library, microphone audio or search history. Device tokens are stored as SHA-256 hashes on the server, in macOS Keychain or in a current-user Windows DPAPI encrypted file on the computer. Sessions expire after 30 days; sign in again afterward. Tokens never reach the phone remote.

## Free and Pro tester status

The server is authoritative for plan status. A tester code grants 1–30 days of temporary Pro status. It is single-use, must be redeemed within 7 days and falls back to Free after expiry. There are no charges or automatic renewals. Pro currently demonstrates account plumbing; it does not unlock additional functions in this release.

An administrator can issue codes using a secret stored outside the checkout:

```sh
.venv/bin/python -m scripts.manage_membership \
  --admin-token-file /absolute/private/path/membership-admin-token --days 7
```

The matching `VUPIO_MEMBERSHIP_ADMIN_TOKEN` must be configured as a secret on the official website. Never put it in a desktop build, GitHub source, README, browser storage, command arguments or frontend configuration. The CLI sends it only to the official website over HTTPS. Issued invitation codes can be sent to a tester. The app and ordinary website accounts cannot issue codes.

## Before paid subscriptions

Choose the business country and supported payment provider, then implement hosted checkout and the customer billing portal. Add a separate payment-provider adapter and signed, idempotent webhooks with a unique event ledger, subscription IDs, status and renewal dates. Process refunds, cancellations, failed payments and grace periods server-side. Add server-enforced entitlements for paid services rather than trusting desktop plan labels. Local playback, STOP and a user's existing library should remain available offline.

Payment collection, provider webhooks, invoices/taxes, checkout, purchase restoration, online feature quotas, refresh tokens and email/password sign-in are not implemented here. Decide these before advertising a paid plan. Autopilot is outside this release.

## Backend source and tests

The website source is managed by Sites, separately from this desktop repository. Relevant files are `lib/membership.ts`, `lib/account-api.ts`, `db/schema.ts`, `drizzle/` and `app/api/account/[action]/route.ts`. Migrations are schema-only and immutable after deployment. Run its tests with `node --import tsx --test tests/membership.test.ts`.

Desktop tests cover server membership display, token redaction, session expiry, local sign-out, device revocation, redirect rejection and OS credential integration. Local HTTP routes require the desktop administrator session; paired phone remotes cannot read or mutate account information.

## Pro Alpha 4062

Personal Radar and AI Collections now require server-verified Pro access. Existing free features remain available without an account. The website owner can manage complimentary grants and limited-use promo campaigns. See [the Pro guide](PRO.md) for activation, administration, expiry and current limitations. Billing is not enabled.
