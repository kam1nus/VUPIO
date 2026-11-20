# Pro Alpha: personal Radar and AI Collections

Build 4062 introduces two optional Pro features. Existing Soundboard, Discover, charts, Studio, phone remote and audio routing remain available without an account. Payments are not connected.

## Activate Pro

1. Open **Account** in VUPIO and sign in. Confirm the one-time device code on the official VUPIO site using ChatGPT sign-in.
2. Enter a promo/invitation code in **Account → Promo codes and invitations**. Alternatively, the owner can grant access to your verified account email before or after you sign up.
3. Select **Refresh account**, then open **Trend Radar → For you · Pro** or **AI Collections · Pro**.

Access is checked by the website before new Pro work, with a maximum 60-second in-memory cache. Network access is required to verify it. Free functions and already-created boards continue working when Pro expires. This is an Alpha entitlement system, not tamper-proof DRM for an open-source desktop app.

## Personal Radar

**For you → New topic** saves a name, natural-language description, country and audio type in this computer's profile. Select a topic and **Refresh topic** to generate a feed. The first version refreshes on request; it does not run a scheduler or send notifications.

The local language model plans up to three search queries. Existing search adapters fetch actual source candidates. Local text embeddings and the language model help select relevant, varied sounds. **Like** biases future collections; **Hide** excludes that source identity. **New to your feed** compares source IDs with the topic's previous collection, not global trend growth.

Countries narrow internet queries. Public sources do not supply reliable cross-platform regional popularity metrics. TikTok/Reels/Shorts availability remains subject to the existing adapters; no private APIs, login bypass or invented ranking data are added.

## AI Collections

Describe a game, mood or moment, choose up to 4/8/12 sounds, and enable your library, internet, or both. Requests can use different languages. Collections and feedback remain local to this computer; the website stores account access, not your library.

1. **Generate collection** creates a reviewable candidate set. It can return fewer sounds if evidence is insufficient.
2. **Prepare selected** checks external audio and creates cached previews. Individual failures remain visible; **Replace** uses another real candidate when one is available.
3. **Preview** plays the prepared audio locally. **Edit** opens the existing Studio with the original recording and actual selected range. Track imports preserve the full track under existing source limits (audio-only, up to 20 minutes).
4. Deselect unwanted cards and **Create board**. Existing library audio is reused. External audio is added only at this step. Repeating the operation opens the same board rather than duplicating it.

An interrupted import can leave already-saved clips in All sounds. Retry the collection to finish; successful imports are reused. The board is created only after all selected sounds have saved successfully.

The bundled small local model can return a weak or invalid plan. VUPIO reports fallback to source metadata rather than inventing a result. The optional balanced local model in Settings can improve complex descriptions. No Ollama installation or API key is required. Internet source blocks and quotas are still real limitations; Pro does not guarantee access or audio identity.

## Owner administration

Open [Pro administration](https://vupio-soundboard.denserat4.chatgpt.site/admin) while signed in to the configured owner account. The owner email is stored as a protected server setting, never as an editable desktop preference. The owner receives developer Pro automatically.

- **Give complimentary Pro**: verified email, tester/developer/gift label, 1–3650 days or no expiry, optional private note. Developer is a label, not an administrator role.
- **Create a promo code**: generated or custom 8–40 letters/digits (spaces/hyphens are ignored), campaign label, 1–10,000 activations, redemption deadline of 1–365 days, access duration or permanent access.
- Only a code hash is stored. Copy the plaintext code when it is created; it cannot be recovered later.
- An account can redeem each campaign once. The activation limit is enforced atomically, including simultaneous redemption of the final slot. Access starts at redemption; overlapping grants use the longest expiry, not cumulative durations.
- **Deactivate** prevents future activations; existing grants remain valid. **Revoke** removes an individual grant. Another active grant can still confer Pro. Owner access itself is configured server-side.

The advanced operator CLI retains its old invocation and supports campaigns/grants:

```sh
PYTHONPATH=. python3 scripts/manage_membership.py --admin-token-file /private/path/admin-token --action grant --email tester@example.com --days 30
PYTHONPATH=. python3 scripts/manage_membership.py --admin-token-file /private/path/admin-token --action grant --email developer@example.com --source developer --permanent
PYTHONPATH=. python3 scripts/manage_membership.py --admin-token-file /private/path/admin-token --action create-code --label Alpha --days 30 --max-uses 20 --redeem-days 14
PYTHONPATH=. python3 scripts/manage_membership.py --admin-token-file /private/path/admin-token --action overview
PYTHONPATH=. python3 scripts/manage_membership.py --admin-token-file /private/path/admin-token --action revoke --id GRANT_ID
```

Never bundle the administrator token with the app or commit it. The website's browser owner panel does not expose or require this token. Promo codes cannot grant administration. The API rejects other accounts, missing origin on browser writes and invalid bearer credentials. Phone sessions cannot access Pro administration or AI endpoints.

## Later

Shared boards, Sound Drops, paid checkout, automatic renewal and Autopilot are not included. A paid launch still needs its payment provider, billing webhooks, customer support flows and appropriate deployment/legal setup.
