# Shared boards and Sound Drops (Alpha 4063)

Open **Soundboard → Shared & Drops**. Cloud sharing is separate from the local Wi-Fi phone remote. A shared board can be used across different networks; your computer's local server stays private.

## Private shared boards

1. Create a normal local soundboard with 1–24 clips, each up to two minutes long.
2. In Shared & Drops, expand **Publish from a local board · Pro**, choose **Private shared board**, choose your local board and review its title/description.
3. Select **Publish reviewed collection**. Only the selected board's audio, clip titles, categories and tags are uploaded to VUPIO. Microphone audio and other library files are not shared.
4. Under **Invite a friend**, enter the email they use to sign in to VUPIO. Choose **Viewer** or **Editor**. Copy the board link and send it yourself; VUPIO does not send an invitation email.
5. The recipient signs in through Account, opens Shared & Drops, pastes the link and selects **Review → Import board**. Invitations can be created before the friend signs up. A link alone does not give access to a private board.

Viewers can preview and pull a local copy for free. Editors need Pro to push changes. The existing owner admin panel can give your testers complimentary Pro.

## Sync and conflicts

Sync is manual in this Alpha:

- **Pull latest version** imports the cloud snapshot into the linked local board, including its title, membership and order.
- **Push local changes** publishes your linked local board as the next cloud revision.
- If your local copy is based on an older cloud revision, push is blocked until you pull. Merely reviewing the latest metadata does not make an old local board safe to push.
- If a local board has unsent changes, pulling requires explicit confirmation. Keep a separate local board if you want to preserve a different arrangement. Audio files remain in All sounds.
- Concurrent cloud writes use an atomic revision check. A member removed during a write cannot commit that write.
- Imports and source bindings are reused on retry. A publisher pulling their own board reuses the original local audio. Local edits to sound details are preserved; remote details update fields that still match the prior shared snapshot.
- The linked board and its sync record are committed together. Failed/cancelled imports can leave completed audio imports in All sounds; retrying reuses those files.

The owner can remove invitations or archive/restore a board. These actions stop new cloud access for removed members. Previously downloaded copies remain on recipients' computers.

## Sound Drops

A Sound Drop is an immutable snapshot of up to 12 selected clips:

1. Choose **Sound Drop · anyone with the link** in the publication form.
2. Review the selected sounds and publish.
3. Copy the link. Anyone with it can preview the actual audio on the website without signing in.
4. In VUPIO, paste the link in Shared & Drops, review/preview, select sounds and import them as a board. Receiving a drop does not require an account or Pro.

Use **Disable link** to stop new access or **Restore link** to enable it again. Existing downloaded files cannot be recalled. To change a published drop's contents, create a new drop. **Import as another board** creates a separate local board while reusing already-imported audio.

Links are unlisted, not a public catalog. Shared/drop pages are excluded from search indexing and send a no-referrer policy. A drop link is not an expiring secret; treat anyone you send it to as a potential recipient of its audio.

## Storage and audio limits

Current Alpha limits:

- 24 sounds per shared board; 12 per drop.
- Up to two minutes and 2 MB of encoded audio per clip.
- 100 MB and 256 uploaded audio objects per account.
- Up to 10 shared board records, 20 drop records and 20 invited members per board. Archived boards and disabled drops retain their records and audio so they can be restored.

Shorten longer clips in Studio before publishing. Sharing encodes a copy as Opus/Ogg, strips embedded file metadata and keeps your local original unchanged. Desktop preview/import verifies the downloaded SHA-256 and decodes to bounded 48 kHz stereo WAV; local preview works independently of browser codec support.

**Remove unused uploads** removes completed uploads that are not referenced by any board or drop, plus abandoned uploads after their safety window. Referenced/archived data is retained. A failed publication can leave private uploads that this action can clean up. Upload quota reservations, asset states and reference checks protect against concurrent cleanup/publication.

The website stores account/member identifiers and emails, board/drop metadata and selected audio. Local sync information is stored in the existing library database; encoded/preview files stay in its AI cache. No port forwarding or new audio driver is needed.

## Current limits

No live co-editing, automatic merge, automatic background sync, public community catalog, payments or Autopilot is included. The cloud service is an Alpha; preserve local copies of important audio. Existing local playback, STOP/PANIC, Discord routing and phone controls do not depend on cloud sharing being online.

## Validation

Server tests use local D1 and R2 to verify private access, roles, ownership, revision races, member revocation during a write, drop disable/restore, storage limits and cleanup. Desktop tests exchange actual encoded audio between isolated profiles, check integrity, prohibit arbitrary hosts, prevent account credentials on anonymous drop reads, protect local edits and reuse files on pull/push.

Browser QA covers two separate test accounts, a private invitation, preview, import, editing/push/pull, public drop playback, disabling/restoring a link and a paired phone-sized remote. Physical Discord audio devices were not modified by this change.
