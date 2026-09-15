# Account printer preferences

Use **Settings → Printer & fabrication**, or the printer controls in the
project **Exports** tab, to choose a printer and press **Save printer preference**.
The preference is account-wide, not project-specific or stored in browser local
storage. It follows the account across projects and devices. The local auth mode
uses the existing local account identity and the local SQLite database.

The current reviewed bundles are Creality Ender-3 and Bambu Lab A1, each with a
0.4 mm nozzle, PLA, and the standard process. Saving the bundle stores its stable
printer ID; material/nozzle/process metadata is derived from the reviewed catalog,
not independently editable combinations. Custom printers, temperatures, profile
uploads, arbitrary G-code, executable paths and command-line flags are not
accepted by this account API.

## Database and deployment

Apply `supabase/migrations/20260915211000_user_fabrication_settings.sql` **before
redeploying the backend** when using Supabase. SQLite creates the new table on
startup, including on existing databases. The startup schema contract includes
this table, so missing hosted migrations fail early rather than silently falling
back to nonpersistent settings.

`user_fabrication_settings` stores `owner_user_id` (primary key), `printer_id`, and
`updated_at`. It is independent of data-usage/privacy settings: saving one cannot
reset the other. Supabase RLS is enabled; anonymous/authenticated direct table
access is revoked and the backend service role performs reads/writes after
resolving the authenticated owner. No request can supply a different owner's ID.
SQLite uses an atomic upsert to handle concurrent first saves.

- `GET /api/user/settings/fabrication` returns the preference and reviewed catalog.
  Missing rows return a documented default without writing a record.
- `PUT /api/user/settings/fabrication` accepts only `{ "printer_id": "bambu_a1_04" }`
  (or the supported Ender-3 ID). Unrecognized fields/presets are rejected.
- `GET /api/projects/{id}/exports` includes `preferred_printer_id` for that account.
  A settings-store outage returns a null preference and an explicit
  `preference_error` without hiding the STEP manifest.
- `POST /api/projects/{id}/exports/gcode` accepts `{}` to use the saved preference,
  or an explicit `printer_id` for a one-off export. An override does not silently
  change the account setting. Project ownership checks remain in place.

Settings responses are private/no-store. Failures are shown as failures, not
"Saved". Account/project transitions reset UI state and cancel outdated settings
loads. The export panel no longer restores user-unscoped, potentially obsolete
G-code previews from localStorage. Generated artifact bytes remain stored by the
existing project artifact system; regenerate to retrieve a fresh result/preview.

## Worker installation is separate from account preferences

No `FORMA_ORCA_SLICER_PATH` or `FORMA_ORCA_PROFILE_ROOT` is required or consumed by
this flow. Forma discovers OrcaSlicer on PATH or in conventional Windows, macOS,
and Linux installation locations, then discovers the bundled system profiles
relative to the executable or standard shared-resource directories. Existing
custom installations that used those overrides should use a conventional install
or expose the trusted installation through PATH. Trusted programmatic/CLI adapter
callers can still pass an explicit executable; the hosted account API cannot.

**Saving settings does not install OrcaSlicer.** The actual fabrication worker
(not a user's browser or a separate Vercel frontend) must have OrcaSlicer, its
bundled profiles, and the native CAD runtime installed. Missing software/profile
files keep G-code generation unavailable. The UI separates this worker state
from saved account preferences and allows saving preferences and downloading
STEP while slicing is unavailable. Worker filesystem paths are not returned in
user-facing availability diagnostics.

## Tests

```bash
python -m pytest tests/api/test_fabrication_settings_api.py tests/api/test_user_settings_api.py tests/projects/test_orca_discovery.py tests/projects/test_demo_printer_exports.py tests/projects/test_fabrication.py tests/projects/test_readiness_build.py -q
cd apps/web
node --experimental-strip-types --test test/fabrication-settings.test.ts
npx playwright test --config playwright.fabrication.config.mjs
npm run build
```

The API tests use real SQLite persistence and authenticated FastAPI routes; the
Supabase tests verify the client contract and migration ACLs, not a live hosted
Supabase deployment. Browser tests run the real fields/hook/export panel with
mocked authentication and backend responses. Orca CLI tests use fixture profiles
and a mocked subprocess; they are not evidence of a physical print or a live
OrcaSlicer installation. Existing native CAD CI remains separate.
