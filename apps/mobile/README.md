# Attendance SaaS — Mobile Application (Flutter)

Native cross-platform mobile application for Android and iOS built with Flutter and Dart.

---

## 1. Installation Requirements

### 1.1 macOS Setup (iOS & Android)
1. **Install Flutter SDK** (>= 3.19.0):
   ```bash
   brew install --cask flutter
   ```
   Or download the official SDK bundle from [Flutter macOS Install](https://docs.flutter.dev/get-started/install/macos).

2. **Verify Environment**:
   ```bash
   flutter doctor
   ```

3. **Android Development Prerequisites**:
   - Install **Android Studio** with the Android SDK, Android SDK Platform-Tools, and Android SDK Build-Tools.
   - Set up an Android Virtual Device (AVD) emulator or connect a physical Android device with USB Debugging enabled.

4. **iOS Development Prerequisites**:
   - Install **Xcode** from the Mac App Store.
   - Install CocoaPods: `sudo gem install cocoapods` or `brew install cocoapods`.
   - Set up an iOS Simulator via Xcode (`open -a Simulator`).

---

## 2. Project Structure

The mobile app follows a clean, maintainable **feature-based architecture**:

```text
apps/mobile/
├── pubspec.yaml            # Flutter package manifest and dependencies
├── analysis_options.yaml   # Dart lint rules
├── lib/
│   ├── main.dart           # App entrypoint and MaterialApp theme
│   ├── core/
│   │   ├── config/         # Environment configuration (EnvConfig with API_BASE_URL)
│   │   └── constants/      # App color palette and shared tokens
│   ├── features/
│   │   └── welcome/        # Phase 1 welcome/home screen
│   │       └── presentation/
│   │           └── welcome_screen.dart
│   └── shared/             # Reusable UI widgets and utility functions
└── test/
    └── widget_test.dart    # Widget verification test
```

---

## 3. Running the Application

### 3.1 Install Dependencies
```bash
flutter pub get
```

### 3.2 Run on Android
```bash
# Connect an Android device or start an emulator, then run:
flutter run -d android --dart-define=API_BASE_URL=http://10.0.2.2:8000
```
*Note: `10.0.2.2` is the special Android emulator loopback address pointing to host `localhost`.*

### 3.3 Run on iOS
```bash
# Start the iOS simulator, then run:
flutter run -d ios --dart-define=API_BASE_URL=http://localhost:8000
```

### 3.4 Run on Web (Development & Testing)
```bash
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

---

## 4. Testing & Code Quality

```bash
# Run unit and widget tests
flutter test

# Run static analysis
flutter analyze
```

---

## 5. Phase Scope & Roadmap

- **Phase 1 (Current)**: Welcome screen, responsive controls, configurable API base URL, and navigation foundation.
- **Phase 6**: Check-in/out engine, PostGIS geofencing, and offline-first SQLite synchronization.
- **Phase 7**: Device binding, mock-GPS detection, and selfie capture.
- **Phase 17**: In-shift random presence challenges.
