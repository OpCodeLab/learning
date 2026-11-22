# OpCode Learn for Android

Native app (Kotlin, Jetpack Compose, Media3 player) for students. It uses the same accounts,
courses and rules as learn.opcode-labs.com through the JSON API in `app/learn/api.py`.

| Screen | What it does |
|---|---|
| Sign in | Email + password (admins also enter their authenticator code) |
| My courses | Cards with cover, progress and end date; pull to refresh; "update available" banner |
| Course | Description, progress, *Continue* button, sections with ticks and attachment markers |
| Player | The whole course as one playlist (next/previous, auto-advance), resume, speed (⚙), fullscreen in landscape, lesson files (opened in a PDF/zip viewer), lesson list |

## Look
Same design as the website and the lab site (lab.opcode-labs.com): black top bars, gold `#FCD23C` buttons,
square corners. The launcher icon is the OpCode Labs logo on black (`res/drawable/ic_launcher_foreground.xml`,
with a white version for Android's themed icons); `res/drawable/opcode_mark.xml` is the same logo for screens.
Both use the paths of `app/learn/static/logo.svg`.

## Protections (same as the website, plus one)
- **Counts as a device** in the 2-device limit (shown as "App on Pixel 7 (Android 14)").
- **One video at a time**: it claims playback (`/api/play`) and pings every 15 s. If another device takes over,
  it pauses and offers *Watch here instead*.
- **Email watermark** over the video, moving every 40 s.
- **No screenshots or screen recording** (`FLAG_SECURE`): recordings of the app show black. Release builds only.
- The sign-in token stays in app-private storage and is excluded from backups and device transfer. The app uses HTTPS only.

## Build (WSL)
The toolchain is in `~/android` in WSL: JDK 17, the Android SDK (platform 35, build-tools 35) and Gradle 8.11.1.
```bash
bash android/build-apk.sh release     # -> android/dist/opcode-learn-<version>.apk (signed)
bash android/build-apk.sh debug       # screenshots allowed, for testing
bash android/build-apk.sh debug -PbaseUrl=http://10.0.2.2:18095   # emulator against a local test server
```

## Signing key: back it up!
`android/keystore/opcode-learn-release.jks` and `android/keystore.properties` (with its password) were generated on
2026-11-22 and are **not in Git**. Keep a copy of both somewhere private, such as a password manager or an encrypted USB key.
If they're lost, a new key can't update the installed app: every student would have to uninstall and reinstall it.

## Publish a new version
1. In `app/build.gradle.kts`, raise `versionCode` (+1) and `versionName`.
2. `bash android/build-apk.sh release`
3. Copy `android/dist/opcode-learn-<version>.apk` to `app/learn/static/app/`, delete the old APK there, and update
   `app/learn/static/app/version.json` (`version_code`, `version_name`, `file`, `size`, `sha256` from the build output).
4. Commit, then deploy the site (docs/install.md step 2 + `vps/install.sh`).

Installed apps see the higher `version_code` at `/api/v1/app` and show an *update available* banner.
Students download it from https://learn.opcode-labs.com/android.

## Google Play later
The same signed build can be uploaded as an `.aab` (`./gradlew bundleRelease`). You need a Google Play developer
account (you create it yourself), a privacy-policy page, and the store listing.
