# RDR-Transit: Mobile & Multiplatform Technical Reference

> **Companion Document to [`docs/SYSTEM_DOCUMENTATION.md`](file:///home/victor/antigravity/RDR-transit/docs/SYSTEM_DOCUMENTATION.md)**  
> **Target Audience:** Mobile Developers, Autonomous Agents, Cross-Platform Contributors  
> **Coverage:** Full walkthrough of `apps/flutter_transit/` (Dart, Android, iOS, macOS).

---

## 1. Overview & Architectural Role

`apps/flutter_transit/` provides a native mobile and desktop client written in **Flutter / Dart** that speaks the identical LAN-Share wire protocol (`<ib` binary framing on TCP `17116` and UDP `56780`).

This enables zero-configuration file sharing directly between:
- Android phones / tablets
- iPhones / iPads
- MacBooks / macOS desktops
- Linux / Windows PCs running Python `rdr-transit`

---

## 2. Source Code Architecture (`apps/flutter_transit/lib/`)

```
apps/flutter_transit/lib/
├── main.dart                       # App entrypoint, Material 3 Dark theme, tab navigation
├── protocol/
│   └── packets.dart                # Dart implementation of <ib packet framing & serialization
└── services/
    ├── discovery_service.dart      # UDP 56780 beacon broadcaster & listener (RawDatagramSocket)
    └── transfer_service.dart       # TCP 17116 client/server streaming, file IO, progress tracking
```

### 2.1 Dart Protocol Framing (`lib/protocol/packets.dart`)

```dart
class LANProtocol {
  static const int headerStructSize = 5;

  static Uint8List framePacket(PacketType type, Uint8List payload) {
    final builder = BytesBuilder();
    final headerBytes = ByteData(5);
    headerBytes.setInt32(0, payload.length, Endian.little);
    headerBytes.setInt8(4, type.value);
    builder.add(headerBytes.buffer.asUint8List());
    if (payload.isNotEmpty) builder.add(payload);
    return builder.toBytes();
  }
}
```
- Exactly mirrors Python's `struct.Struct("<ib")`.
- `parsePacketHeader(Uint8List)` decodes the 5-byte header into `PacketHeader(payloadLength, type)`.
- Handles `header`, `data`, `finish`, `cancel`, `skip`, and `snippet` packets.

### 2.2 Peer Discovery Engine (`lib/services/discovery_service.dart`)
- **`RawDatagramSocket`**: Binds to `0.0.0.0:56780` with `reuseAddress: true` and `reusePort: true`.
- **Broadcast Transmission**: Constructs JSON payload with `{id, name, os, port}` and transmits to `255.255.255.255:56780` via `_socket.send()`.
- **Peer State Store**: Collects received datagrams, updates `lastSeen` timestamps, and prunes peers inactive for >25 seconds. Emits reactive updates via `ChangeNotifier`.

### 2.3 Transfer Engine (`lib/services/transfer_service.dart`)
- **TCP Receiver (`ServerSocket.bind`)**:
  - Listens on port `17116`.
  - Accumulates byte stream in a `BytesBuilder`.
  - Parses 5-byte headers; when full payload arrives, processes according to `PacketType`:
    - `PacketType.header`: Opens target file in app storage / downloads directory.
    - `PacketType.data`: Appends chunk to file writer.
    - `PacketType.finish`: Flushes file, records `ReceivedItem`, and sends back `Finish` ACK.
    - `PacketType.snippet`: Parses JSON text and notifies UI.
- **TCP Sender (`Socket.connect`)**:
  - Connects to target IP on port `17116`.
  - Sends `Header` packet.
  - Streams file in chunks via `file.openRead()`, packing each into `PacketType.data`.
  - Tracks transfer throughput (MB/s) and percentage progress via `FileTransferProgress`.
  - Sends `Finish` packet.

---

## 3. Platform Configuration & Permissions

### 3.1 Android (`android/app/src/main/AndroidManifest.xml`)
Android requires explicit network and storage capabilities for LAN transfers:
- **`CHANGE_WIFI_MULTICAST_STATE`**: Critical for receiving UDP discovery broadcasts on modern Android Wi-Fi chipsets.
- **`INTERNET` & `ACCESS_NETWORK_STATE`**: Standard socket communication.
- **`WAKE_LOCK`**: Prevents the OS from suspending active high-speed TCP file transfers when the screen turns off.
- **`READ_MEDIA_*` / Scoped Storage**: Allows picking documents, photos, and videos.

### 3.2 Apple iOS (`ios/Runner/Info.plist`)
Apple enforces strict sandboxing and user privacy for local area network access:
- **`NSLocalNetworkUsageDescription`**: Mandatory since iOS 14. Displays the user consent dialog: *"RDR Transit requires access to your local Wi-Fi network to discover nearby devices and transfer files at high speed."*
- **`UIFileSharingEnabled` & `LSSupportsOpeningDocumentsInPlace`**: Configures the iOS app so all received files appear directly in the native Apple **Files** app under *"On My iPhone/iPad > RDR Transit"*.
- **`NSBonjourServices`**: Declares local service identifiers `_lanshare._tcp` and `_rdrtransit._udp`.

### 3.3 Apple macOS (`macos/Runner/Release.entitlements`)
- `com.apple.security.network.client`: Permits outbound TCP connections.
- `com.apple.security.network.server`: Permits binding server sockets for receiving files.
- `com.apple.security.files.downloads.read-write`: Grants write access to the Downloads folder.
