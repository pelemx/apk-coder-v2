# JuprisX Pygame Agent — Android / Google Play 2026 Build Fix

## What was broken

The failing build was **not a normal host Cython problem**.

`python-for-android` was invoking the generated **hostpython**:

`.../hostpython3/.../bin/python setup.py build_ext -v`

but Cython was only declared as a p4a requirement. The pygame recipe then reached `setup.py build_ext` without Cython available in that hostpython environment.

The project also used Android API 34 as its fallback policy. For a new Google Play app/update after **31 August 2026**, the target must be **Android 16 / API 36**.

## Fixes applied

1. Target API: **36**
2. Minimum API: **24**
3. Architectures: **arm64-v8a + armeabi-v7a**
4. Release artifact: **AAB**
5. Test artifact: **APK**
6. Android NDK: **r28c (Buildozer token: 28c)**
   - NDK r28+ is required here because it provides 16 KB ELF alignment by default.
7. pygame: **2.6.1**
8. Cython for pygame build: **3.0.12**
9. Added `p4a-recipes/pygame/__init__.py`
   - overrides the old p4a pygame recipe
   - installs Cython into hostpython before `setup.py build_ext`
   - builds pygame 2.6.1 from its source archive
   - restores pygame 2.6.1 SIMD blitter sources in the Android surface extension
10. Generated `buildozer.spec` now always contains:
    - `p4a.local_recipes = ./p4a-recipes`
    - `android.api = 36`
    - `android.minapi = 24`
    - `android.ndk = 28c`
11. Release artifacts are verified:
    - APK: signature + zip alignment check
    - AAB: JAR signature check
12. The build UI should treat **AAB as a Play upload artifact**, not as an installable file.

## Important distinction

- `*.aab` -> upload to Google Play Console.
- `*.apk` -> install/test on an Android device.

Trying to install the AAB directly will result in an invalid/unsupported package message on normal Android package installers.

## Clean rebuild

After replacing the agent with this version, rebuild the affected project from a clean Android build cache:

```bash
buildozer android clean
buildozer -v android release
```

The JuprisX builder normally runs the build inside:

```text
~/.juprisx/build/<project>/
```

and keeps the SDK/NDK cache on the Linux filesystem.

## Verification target

A successful build is only the first gate.

The production flow is:

```text
Pygame source
   -> static analysis / Android refactor
   -> Buildozer + python-for-android
   -> pygame 2.6.1 + SDL2 native build
   -> arm64-v8a / armeabi-v7a
   -> API 36 target
   -> 16 KB-compatible native libraries
   -> signed APK validation
   -> signed AAB validation
   -> device install/run test
   -> Play Console upload
```

Google Play policy and Android compatibility still require the final generated artifact and app behavior to be tested; a green compiler result alone is not proof of runtime compatibility.


## NDK 404 hotfix

Buildozer's `android.ndk` setting is a version token, not the archive name. The correct value is `28c`.
If `r28c` is supplied, Buildozer constructs `android-ndk-rr28c-linux.zip`, which does not exist and returns HTTP 404.
JuprisX now normalizes either `28c` or `r28c` to `28c` before writing `buildozer.spec`.
