# Ascend privacy and customer defaults

Ascend settings use the current Windows user's QSettings store under AscendToolkit/AscendToolkit. Console profiles, manager URL, device selections, playlist paths, payload paths/notes/hashes and appearance settings are stored locally. The app does not include an Ascend telemetry or automatic-upload endpoint.

Local settings are not read from the customer ZIP and are not bundled by the release script. A fresh customer installation asks for console details and starts with an empty manager address, playlist and payload catalogue. Existing local preferences on a developer's machine are separate from the shipped sources.

Embedded Web Manager and ListenFree use separate off-the-record Qt browser profiles with no persistent cookies. These profiles are not copied between customers or packaged. Sites can still use cookies/storage during the running session. Customers should close Ascend after using shared computers. Downloads explicitly saved by a user remain on disk.

Online services receive normal browser network requests when opened, including the connecting IP address and browser information. ListenFree controls its own advertising/consent and privacy practices; Ascend does not accept consent automatically. Manager URLs are connected only when configured by the user. Ascend does not send its local console profile, music queue or payload catalogue to these services automatically. Uploading through a manager's file picker is a user-directed action handled by that manager.

Spotify opens in the user's external browser. Its browser profile, sign-in, cookies and account data remain controlled by that browser and Spotify. Ascend does not implement OAuth or store Spotify account tokens.

A copied diagnostic report may contain capture-card/audio-device descriptions. Exported payload catalogues contain local file paths and notes. These actions are explicit; check exported files before sharing them. Recordings and screenshots contain whatever the capture input is showing.

The development folder may contain private test captures, logs, older source backups and local scratch scripts. Do not distribute that folder. The customer release archive excludes those files by an explicit allowlist and is checked for developer paths and configured private IP addresses before delivery.

ListenFree native audio: the embedded page may request playback of direct HTTPS media on listenfree.in or saavncdn.com and their subdomains. The Qt WebChannel bridge exposes only audio source/play/pause/seek/volume/rate commands and playback-state signals; it provides no local-file, settings or account API. Native playback is rejected when the active page is not ListenFree, or when a stream uses an unsupported origin, local file path or non-HTTPS scheme. Stream URLs are held in memory for playback and are not added to the user's payload catalogue, music queue or customer archive. Qt may buffer network audio during playback; Ascend does not save streamed music files. The website can change its APIs, so future changes may require an app update.

FTP connections go directly from this PC to the host you enter. Host, port and username can be remembered locally; passwords stay in memory. No FTP connection starts automatically. Your console files and credentials are excluded from customer source packages.
