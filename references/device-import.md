# Getting the deck onto a device

The `.apkg` works in every Anki client. There is no app called "AnkiWeb Mobile". Phones
and tablets use **AnkiMobile** (iPhone/iPad, the paid official app) or **AnkiDroid**
(Android, free). Both sync with a free **AnkiWeb** account. The AnkiWeb website itself
cannot import `.apkg` files.

## iPhone / iPad (AnkiMobile)

1. Send the `.apkg` to the device: AirDrop it from the Mac, or put it in iCloud Drive or
   email it to yourself.
2. Tap the file, then **Share > AnkiMobile** (or "Open in AnkiMobile"). It imports immediately.
3. Optional: in AnkiMobile, **Sync**, to back it up to AnkiWeb and reach other devices.

## Android (AnkiDroid)

1. Put the `.apkg` on the device: Google Drive, email, or USB.
2. In AnkiDroid, open the **three-dot menu > Import**, and pick the file. Tapping the file in a
   file manager and choosing AnkiDroid also works.
3. Optional: **Sync** to AnkiWeb.

## Through a computer (any device)

1. Install Anki desktop (free) from apps.ankiweb.net.
2. Double-click the `.apkg` (or use **File > Import**).
3. Click **Sync**, and sign in with the learner's AnkiWeb account.
4. On the phone or tablet, sign in with the same account and tap **Sync**.

## Straight into Anki on this computer (`adb deliver`)

At the end of a run, the skill can also put the deck into Anki desktop on the computer
it ran on, if the user agrees:

- **Open it in Anki.** No setup. Anki shows its import dialog; click **Import**, then
  **Sync** to send it to AnkiWeb.
- **Import it, and optionally sync, through AnkiConnect.** This needs the AnkiConnect
  add-on, set up once: in Anki, **Tools > Add-ons > Get Add-ons...**, enter code
  `2055492159`, then restart Anki. Keep Anki open while the skill imports. It checks that
  every note arrived, then syncs with the AnkiWeb login Anki already has. The skill
  never sees the password. If Anki asks about a full sync, answer in Anki's own window.

On **WSL** (Windows Subsystem for Linux), both work with Anki installed on Windows: the
deck is handed to Windows to open, or to import, as long as WSL's interop is on (it is
unless `/etc/wsl.conf` sets `[interop] enabled=false`). WSL2 reaches AnkiConnect on
Windows only with mirrored networking (Windows 11 22H2 or later): add
`networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig`, then run
`wsl --shutdown` and reopen the terminal.

Once it's on AnkiWeb, the phone or tablet only needs a **Sync**.

## Updating later

Re-import the rebuilt `.apkg` the same way. Notes keep stable IDs, so existing cards
update in place and review history is kept. Don't delete the old deck first: that
discards the history.

## Pace advice for a test date

Anki introduces **20 new cards a day** by default, so a 300-card deck takes about 15
days to introduce. If the test is sooner:

- Raise **New cards/day** in the deck's options (the gear next to the deck, then
  Options), to about `cards / (days until the test - 2)`. That leaves the last two days
  for reviews only.
- Or use **Custom Study > Increase today's new card limit** for a one-off push.
- Studying the parent deck covers every subdeck. To focus on one source, study its
  subdeck alone.
