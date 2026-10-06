# JuprisX APK Coder

AI-driven HTML/JS/CSS to Android APK/AAB builder.

## Architecture

```text
User Chat / Prompt
        |
        v
JuprisX / MCP / R9 Agent
        |
        +--> HTML5 / JavaScript / CSS / Canvas / Phaser
        +--> Images / Icons / Audio / Metadata
        |
        v
Web Project
        |
        v
Web Validator / Auto Fix
        |
        v
Native Android WebView Container
        |
        +--> WebViewAssetLoader
        +--> local/offline assets
        +--> Android back handling
        +--> splash / lifecycle
        |
        v
Project-bound JKS
        |
        v
Gradle
   +----+----+
   |         |
  APK       AAB
```

## What changed

The Android application packaging path is being migrated away from Pygame, Buildozer, and python-for-android (p4a).

The desktop builder itself remains Python. Python is the orchestration/tooling layer; generated applications are HTML5/JavaScript/CSS applications running inside a native Android WebView container.

MCP/JuprISX remains the AI/agentic backbone. The builder does not replace the existing brain with a second agent.

## Generated project layout

```text
project/
├── web/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.json
│   └── assets/
│       ├── images/
│       ├── audio/
│       ├── icons/
│       └── fonts/
├── android/
│   └── ... native WebView Gradle project ...
├── signing/
│   └── <project>.jks
└── build/
    ├── apk/
    └── aab/
```

## Build pipeline

1. Chat with the AI and describe the application/game.
2. Generate HTML, JavaScript, CSS and local assets.
3. Validate entry point, viewport, asset paths, CDN dependencies and manifest integrity.
4. Copy the web project into the Android WebView template.
5. Create or reuse the project-bound release keystore.
6. Run Gradle `assembleRelease` for APK.
7. Run Gradle `bundleRelease` for AAB.

The same project must reuse the same signing identity for future Play Store updates. Existing keystores must never be overwritten automatically.

## Offline-first rules

- `web/index.html` is mandatory.
- Generated application assets must use relative/local paths.
- No HTTP resources.
- No remote CDN dependency for packaged applications.
- JavaScript libraries such as Phaser must be bundled locally when used.
- Mobile viewport configuration is required.
- Broken local asset references are build-blocking findings.

## Android container

The native container loads packaged web content through AndroidX WebView infrastructure and `WebViewAssetLoader`, rather than depending on a remote website.

The WebView layer is responsible for native lifecycle behavior, Android back navigation, and local asset routing. Application logic remains in the generated HTML/JS/CSS project.

## Artifacts

```text
APK  -> device testing / sideload distribution
AAB  -> Google Play Console release
```

## Development status

The HTML/JS Android refactor is developed on the isolated branch:

`refactor/html-js-android-builder`

The migration is intentionally kept separate from `main` until the native Gradle template and end-to-end APK/AAB build are verified in the target build environment.
