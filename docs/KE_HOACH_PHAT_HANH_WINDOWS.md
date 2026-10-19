# Windows release and update plan — 2026-10-19

Goal: Windows x64 ZIP containing LiveStudio.exe, a separate updater, Python/Qt runtime and FFmpeg/FFprobe. No Python installation required. Data stays in LocalAppData/TikTokLiveStudio; videos stay in the selected folder.

Design approved in conversation: optional update prompt, safe recording finalization, restart and preservation of customer data. Implementation proceeds inline under the user's instruction to perform the work, without another approval round.

## Decisions

- PyInstaller onedir for the main app; separate onefile updater copied to a temporary directory before the app exits. Replace the whole marked application folder after the old PID exits; preserve the previous folder for rollback.
- Independent Ed25519 update signing key, kept only in ignored `.release-signing/`; public verification key embedded in the package. HTTPS alone does not authorize executable updates. Never distribute GitHub credentials.
- Signed manifest fixes version, platform, ZIP hash and size. Download only from the configured HTTPS license host. Reject downgrade, malformed archives, traversal, symlinks, unexpected package layout and corrupted downloads.
- Hosting stores signed manifests and ZIPs in `/app/data/releases`. Authenticated admin publishes with CSRF-protected streaming upload; public clients fetch the manifest and package. Private source repo remains private.
- First published version 1.0.0; client checks at startup and in Settings. User agrees before download/install. If recording, finish MP4 before closing. New application writes startup acknowledgment; absent acknowledgment causes rollback and relaunch of previous version.
- Windows 10/11 x64 target. Unsigned Windows EXEs may show SmartScreen; publisher certificate is a separate purchase and is not implied by update signatures.

## Tasks and verification

- [x] Shared signed-manifest verification and streaming publication API. Tests: tampering, downgrade, CSRF, upload size/hash, public download, existing admin regression suite.
- [x] Desktop updater and safe replacement helper. Tests: malicious archive, hash mismatch, preserved settings, successful replacement and rollback.
- [x] UI and runtime: background checking/downloading, explicit consent, finalize workers, bundled FFmpeg PATH, frozen startup command, startup acknowledgment and useful crash log.
- [x] Repeatable build command, dependency lock, public config, notices and private signing command. Build real Windows ZIP, scan contents for owner secrets; smoke-test frozen GUI, worker spawn and media output.
- [ ] Full suite, separate final review, publish source/config instructions. Hosting changes require the owner to set only the public update verification key and Redeploy; upload release through admin after verification.

## Review focus

ZIP paths on Windows (drive, backslash, case collisions); read-only install folder; internet failure while downloading; program still recording; new EXE fails before startup acknowledgment. No deletion of customer video/data directories or previous install backup.

## Progress

Initial baseline: hosting deployed successfully by owner; local suite previously 159 passed, 1 Docker-only test skipped. No packaging/update implementation existed at start.

Implemented and checked: signed releases, authenticated chunk upload capped at 256 KiB per request, client download/hash verification, safe folder replacement, rollback tests, Qt update controls, frozen startup/FFmpeg PATH, embedded HTTPS configuration, isolated frozen self-test and real updater 1.0.0 → QA 1.0.1 with preserved settings. Final optimized artifact rebuild and final verification follow.

Independent review: fixed acknowledgment before initialization, removed 512 MiB unauthenticated transport buffering using small chunks, added download cancellation. Follow-up found Waitress's inclusive request limit; production cap is now CHUNK_SIZE + 1, with a real Waitress HTTP boundary test. Refuse replacement when the marked installation contains additional customer files; keep previous installation.

Final local verification: 179 passed, 1 Docker-only test skipped; Ruff check/format passed. Final artifact `dist/release/LiveStudio-1.0.0/LiveStudio-1.0.0-Windows-x64.zip`, 159885633 bytes, 1246 files. Signature/hash and scan against owner's actual private material passed. Final frozen runtime and updater diagnostic passed, upgrading to isolated QA 1.0.1 with preserved channels/settings. Publishing the first release on HTTPS admin remains an owner action after environment configuration and redeploy; this has not been claimed as tested on Vibe Host yet.
