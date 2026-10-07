# JuprisX APK-Coder-X2

HTML5 / CSS / JavaScript → Android APK & AAB builder for Windows.

JuprisX APK-Coder-X2 is a desktop builder that takes a local web app or AI-generated web project and packages it into a native Android application using an embedded WebView container and Gradle. The generated app payload is designed for local/offline-first execution; Android packaging is handled by the native template.

## What it does

The production pipeline is:

```
User / AI
   │
   ▼
HTML5 + CSS + JavaScript project
   │
   ├── web/index.html
   ├── web/app.js
   ├── web/style.css
   └── web/assets/*
   │
   ▼
WebValidator
   │
   ▼
Native Android WebView template
   │
   ▼
Project signing / JKS
   │
   ▼
Gradle
   │
   ├── APK
   └── AAB
```

The Android application loads the packaged web app through `WebViewAssetLoader` using the local `appassets.androidplatform.net` asset origin.

## Main capabilities

### HTML5 / JavaScript application generation

Generated application code follows the builder contract:

- HTML5, CSS and JavaScript for the web payload
- `web/index.html` as the entry point
- Mobile viewport support
- Canvas/DOM and pointer/touch input
- Local project assets
- Relative asset paths
- No CDN requirement for runtime assets
- Offline-first Android WebView packaging

The canonical starter project is in:

```
web_templates/starter/
```

## Web project layout

A generated project uses:

```
project/
├── web/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.json
│   └── assets/
│       ├── images/
│       ├── audio/
│       ├── fonts/
│       └── icons/
├── android/                 # generated native Android container
├── signing/                 # project signing identity
├── playstore_assets/        # Play Store artwork
├── result_build/            # generated APK/AAB output
└── .juprisx/
```

## Architecture

```
main.py
  └── gui.app.AppWindow
      ├── part3_project
      │   ├── project manager
      │   ├── project table
      │   ├── reviewer
      │   └── workflow/state handling
      │
      ├── part4_chat
      │   ├── chat UI
      │   ├── action detection
      │   ├── project generation flow
      │   └── AI/agent interaction
      │
      ├── part1_builder
      │   ├── CompilerPipeline
      │   ├── keystore handling
      │   ├── Android/Play policy
      │   └── WSL connector
      │
      ├── core_engine
      │   ├── GradleBuilder
      │   ├── KeystoreManager
      │   ├── WebProjectGenerator
      │   └── WebValidator
      │
      └── part5_assets
          ├── automatic assets
          ├── app/launcher icons
          └── Play Store asset pipeline
```

## Repository structure

| Path | Responsibility |
|---|---|
| `main.py` | Desktop application entry point |
| `gui/` | Main desktop UI |
| `part1_builder/` | Android compilation, signing, WSL/build environment integration |
| `part2_generator/` | HTML/JS generation, analysis and AI fix prompts |
| `part3_project/` | Project registration, scan, review, build workflow and rollback |
| `part4_chat/` | Chat interface and executable builder actions |
| `part5_assets/` | Generated assets, launcher icons and Play Store asset preparation |
| `core_engine/` | Native Web/Android core services |
| `templates/android_webview/` | Native Android WebView application template |
| `web_templates/starter/` | Starter HTML/CSS/JS project |
| `part1_builder/android_policy.json` | Android/Play target policy values |
| `config.json` | MCP/assets endpoint configuration |
| `rules_.txt` | Builder operating rules |
| `juprisx_pygame-gen.md` | Legacy/reference generation skill document |

## Native Android container

The Android packaging template is:

```
templates/android_webview/
```

The native container uses:

- Android Gradle Plugin 8.13.0
- Kotlin Android plugin 2.2.20
- compile SDK 36
- target SDK 36
- Java/Kotlin JVM target 17
- AndroidX Activity
- AndroidX WebKit
- `WebViewAssetLoader`

The generated `MainActivity`:

1. Creates a WebView.
2. Enables JavaScript and DOM storage.
3. Uses `WebViewAssetLoader` for packaged assets.
4. Disables direct file/content access.
5. Loads:

```
https://appassets.androidplatform.net/assets/www/index.html
```

6. Preserves normal Android back navigation through WebView history.

## Build pipeline

The compiler entry point is:

```
part1_builder/compiler.py
```

`CompilerPipeline` performs the release build sequence:

1. Validate the web project.
2. Create/update the native Android project from the WebView template.
3. Copy `web/` into Android assets.
4. Resolve application name and package ID from `manifest.json`.
5. Install launcher icons when available.
6. Reuse the existing project keystore or create one when necessary.
7. Write Android signing properties.
8. Invoke `GradleBuilder`.
9. Return APK/AAB output paths.

Buildozer/p4a is not used by the production HTML/JS packaging path.

## Signing

Each project has a project-bound release signing identity.

Typical layout:

```
signing/
├── <project>.jks
└── signing.properties
```

The signing manager refuses to overwrite an existing keystore and reuses the existing signing information for subsequent builds. This is important for publishing updates to the same Android application.

Keep the JKS and its passwords backed up securely. Losing the signing identity can prevent publishing future updates under the same signing configuration.

## Gradle and Windows/WSL

The production build can use the native Windows Android toolchain when complete.

When the Windows toolchain is incomplete, the builder falls back to WSL.

The WSL path is designed for Windows project directories containing spaces and shell-sensitive characters. Project paths are handled without relying on unsafe shell argument forwarding.

The Gradle builder also prepares the WSL Android build environment, including the Android SDK/toolchain required by the Gradle build.

For a WSL build, the generated Android project receives a valid:

```
android/local.properties
```

with the active WSL Android SDK location before Gradle executes.

## Validation

Before packaging, `core_engine/web_validator.py` checks the generated web application.

Examples of checks include:

- missing `index.html`
- missing mobile viewport metadata
- remote/CDN script dependencies
- insecure HTTP resources
- absolute desktop paths
- broken local asset references
- invalid `manifest.json`
- missing required manifest fields

The static analyzer in `part2_generator/analyzer.py` applies the same immutable HTML/JS Android builder contract to project analysis and AI fixes.

## Package identity

The web manifest can provide the Android package name:

```json
{
  "name": "My App",
  "short_name": "My App",
  "start_url": "index.html",
  "display": "fullscreen",
  "orientation": "portrait",
  "offline": true,
  "package": "com.juprisx.my_app"
}
```

When no package is supplied, the builder derives one from the application name.

## Automatic project assets

AI-generated projects can request additional artwork. The asset subsystem can generate and record project assets such as:

- application icon
- in-game images
- launcher icon resources
- Play Store artwork

Generated in-game images are stored under:

```
web/assets/images/
```

## Play Store assets

The Play Store asset pipeline is implemented in:

```
part5_assets/playstore_assets.py
```

It provides image preparation and validation for the project publishing workflow, including:

| Asset | Production pipeline target |
|---|---|
| App icon | 512 × 512 PNG |
| Feature graphic | 1024 × 500 |
| Phone screenshots | 9:16 or 16:9, with size/ratio validation |

The module can crop/resize source images, remove alpha where required, save the normalized files, and run a validation checklist.

## Configuration

`config.json` contains runtime configuration for external services used by the desktop application.

Current keys include:

```json
{
  "mcp_url": "",
  "mcp_api_key": "",
  "mcp_timeout_chat": 80,
  "mcp_timeout_generate": 190,
  "assets_api_url": "",
  "assets_api_key": "",
  "assets_timeout": 120
}
```

Set service endpoints/keys for the environment where those services are available.

## Installation

Requirements listed by the application:

```
customtkinter
requests
Pillow
pygame
```

The desktop launcher is:

```
python main.py
```

The application starts the JuprisX desktop builder UI.

For Android release builds, the application can use the Windows Android toolchain or the integrated WSL build path depending on the local environment.

## Typical workflow

1. Start JuprisX.
2. Create or load a project.
3. Generate/import the HTML/CSS/JS application.
4. Run a project scan.
5. Review findings or use AI auto-fix.
6. Prepare/generate project assets as needed.
7. Generate or reuse the project JKS signing identity.
8. Run the release build.
9. Collect the generated APK/AAB from the project output.

The same project signing identity is reused on later builds.

## Release artifacts

Build results are copied into the project's:

```
result_build/
```

Typical outputs:

```
result_build/
├── app-release.apk
└── app-release.aab
```

Exact filenames can depend on the generated Gradle project.

## Design principles

### Immutable builder contract

The production build target is Android WebView + local HTML/CSS/JavaScript.

The web payload is not a Python/Pygame Android runtime.

### Offline-first runtime

The packaged application is expected to run from local WebView assets rather than depending on a live CDN or remote runtime script.

### Project-bound signing

The release keystore belongs to the project and is reused across builds.

### Validation before packaging

The web application is checked before Gradle packaging so common packaging blockers are found earlier.

### Windows-first developer workflow

The desktop application is designed for Windows and can fall back to WSL for Android builds when the Windows toolchain is incomplete.

## Project status

This repository represents the production JuprisX HTML/JS → Android packaging implementation currently used by the project.

The source tree still contains some legacy names and reference files from the earlier Pygame-oriented implementation, but the active production compiler path is the native Android WebView pipeline described above.

## License

No explicit license file is currently present in the repository. Treat the repository as all-rights-reserved unless a separate license is provided by the project owner.
