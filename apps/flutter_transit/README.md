# RDR Transit Mobile & Multiplatform (Flutter) ⚡📱

Cross-platform mobile and desktop application for **RDR Transit / LAN-Share** peer-to-peer file transfer.

Built with **Flutter** (Dart), targeting:
- **Android** (Phones, Tablets)
- **Apple iOS** (iPhone, iPad)
- **Apple macOS** (Silicon & Intel)
- **Windows & Linux**

---

## Features

- **Zero-Config Peer Discovery**: Listens and broadcasts LAN-Share beacons on UDP `56780`.
- **Wire-Compatible Chunk Transfers**: Streams files directly using LAN-Share TCP `17116` packets.
- **Cross-Device Interoperability**: Seamlessly exchanges files between Android, iPhones/iPads, Linux PCs, MacBooks, and Windows machines running `rdr-transit`.
- **Native Document Sharing**:
  - On iOS: Integrates with Apple Files app via `UIFileSharingEnabled`.
  - On Android: Supports media & document pickers with Wi-Fi Multicast lock.
- **Clipboard & Text Snippets**: Instant text sharing across phones and computers.

---

## Prerequisites

- [Flutter SDK](https://docs.flutter.dev/get-started/install) (>= 3.10.0)
- For Android: Android Studio & Android SDK
- For iOS & macOS: Xcode (macOS host)

---

## Getting Started

```bash
cd apps/flutter_transit
flutter pub get
```

### 1. Running on Android

Connect an Android device or start an emulator:
```bash
flutter run -d android
```

To build a standalone APK:
```bash
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk
```

To build an Android App Bundle (for Google Play):
```bash
flutter build appbundle --release
```

### 2. Running on Apple iOS

Connect an iPhone/iPad or open the iOS Simulator:
```bash
flutter run -d ios
```

To build for App Store / TestFlight:
```bash
flutter build ipa --release
```

> **Note on Apple Local Network Privacy**: iOS requires user consent to communicate on the local network. This is declared in `ios/Runner/Info.plist` with `NSLocalNetworkUsageDescription`. When first launched, iOS will prompt: *"RDR Transit would like to find and connect to devices on your local network"*. Tap **Allow**.

### 3. Running on macOS / Desktop

```bash
flutter run -d macos
# or
flutter run -d linux
```

---

## Architecture

- **`lib/protocol/packets.dart`**: Implements the `<ib` binary packet structure compatible with the LAN-Share / RDR-Transit specification.
- **`lib/services/discovery_service.dart`**: Handles UDP 56780 peer beaconing and listening via `RawDatagramSocket`.
- **`lib/services/transfer_service.dart`**: Handles TCP 17116 chunked streaming, file saving, and text snippet transfers.
- **`lib/main.dart`**: Modern Material 3 tabbed user interface (Peers, Send, Receive, Snippets).
