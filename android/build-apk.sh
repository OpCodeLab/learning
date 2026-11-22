#!/usr/bin/env bash
# Build the APK in WSL (faster on the Linux filesystem than on /mnt/d).
#   bash android/build-apk.sh debug      -> android/dist/opcode-learn-debug.apk
#   bash android/build-apk.sh release    -> android/dist/opcode-learn-<version>.apk (signed, needs keystore.properties)
# Extra Gradle args are passed through, e.g. -PbaseUrl=http://10.0.2.2:18095 for the emulator.
set -euo pipefail
type=${1:-debug}; shift || true
SRC=$(cd "$(dirname "$0")" && pwd)
WORK=~/build/opcode-learn-android
export JAVA_HOME=~/android/jdk17 ANDROID_HOME=~/android/sdk
mkdir -p "$WORK"
rsync -a --delete --exclude build --exclude .gradle --exclude dist "$SRC/" "$WORK/"
echo "sdk.dir=$ANDROID_HOME" > "$WORK/local.properties"
cd "$WORK"
chmod +x gradlew
task=assemble${type^}
./gradlew --no-daemon -q "$task" "$@"
mkdir -p "$SRC/dist"
if [[ $type == release ]]; then
    ver=$(grep -oP 'versionName = "\K[^"]+' app/build.gradle.kts)
    out="$SRC/dist/opcode-learn-$ver.apk"
    cp app/build/outputs/apk/release/app-release.apk "$out"
else
    out="$SRC/dist/opcode-learn-debug.apk"
    cp app/build/outputs/apk/debug/app-debug.apk "$out"
fi
ls -l "$out"
sha256sum "$out"
