import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';

class DiscoveredPeer {
  final String ip;
  final String name;
  final String os;
  final int port;
  final String deviceId;
  DateTime lastSeen;

  DiscoveredPeer({
    required this.ip,
    required this.name,
    required this.os,
    this.port = 17116,
    this.deviceId = '',
    DateTime? lastSeen,
  }) : lastSeen = lastSeen ?? DateTime.now();

  bool get isAlive => DateTime.now().difference(lastSeen).inSeconds < 18;

  String get osBadge {
    final lower = os.toLowerCase();
    if (lower.contains('win')) return 'Windows';
    if (lower.contains('mac') || lower.contains('darwin') || lower.contains('ios')) return 'Apple';
    if (lower.contains('android')) return 'Android';
    if (lower.contains('linux')) return 'Linux';
    return os.isEmpty ? 'Unknown' : os;
  }
}

class DiscoveryService extends ChangeNotifier {
  static const int defaultBroadcastPort = 56780;
  static const int defaultTransferPort = 17116;

  final Map<String, DiscoveredPeer> _peers = {};
  RawDatagramSocket? _socket;
  Timer? _beaconTimer;
  Timer? _cleanupTimer;
  bool _running = false;

  String deviceName = Platform.localHostname;
  String osName = Platform.operatingSystem;
  int broadcastPort = defaultBroadcastPort;
  int transferPort = defaultTransferPort;

  List<DiscoveredPeer> get peers => _peers.values.toList()..sort((a, b) => a.name.compareTo(b.name));
  bool get isRunning => _running;

  Future<void> start() async {
    if (_running) return;
    _running = true;

    try {
      _socket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        broadcastPort,
        reuseAddress: true,
        reusePort: true,
      );
      _socket?.broadcastEnabled = true;

      _socket?.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read) {
          final datagram = _socket?.receive();
          if (datagram != null) {
            _handleIncomingBeacon(datagram.data, datagram.address.address);
          }
        }
      });
    } catch (e) {
      debugPrint('Discovery bind error: $e');
    }

    // Send initial beacon
    triggerBeacon();

    // Periodic beacon every 4s
    _beaconTimer = Timer.periodic(const Duration(seconds: 4), (_) => triggerBeacon());

    // Clean up stale peers
    _cleanupTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      final now = DateTime.now();
      final beforeCount = _peers.length;
      _peers.removeWhere((_, peer) => now.difference(peer.lastSeen).inSeconds > 25);
      if (_peers.length != beforeCount) {
        notifyListeners();
      }
    });

    notifyListeners();
  }

  void stop() {
    _running = false;
    _beaconTimer?.cancel();
    _cleanupTimer?.cancel();
    _socket?.close();
    _socket = null;
    notifyListeners();
  }

  void triggerBeacon() {
    try {
      final payload = jsonEncode({
        'id': '{mobile-${Platform.operatingSystem}-${identityHashCode(this)}}',
        'name': deviceName,
        'os': osName,
        'port': broadcastPort,
      });

      final bytes = utf8.encode(payload);
      _socket?.send(bytes, InternetAddress('255.255.255.255'), broadcastPort);
    } catch (e) {
      debugPrint('Error triggering beacon: $e');
    }
  }

  void _handleIncomingBeacon(Uint8List data, String senderIp) {
    try {
      final str = utf8.decode(data, allowMalformed: true);
      final json = jsonDecode(str);
      if (json is Map<String, dynamic> && json.containsKey('name')) {
        final name = json['name'] as String? ?? 'Peer';
        final os = json['os'] as String? ?? 'Unknown';
        final id = json['id'] as String? ?? '';

        final existing = _peers[senderIp];
        if (existing != null) {
          existing.lastSeen = DateTime.now();
        } else {
          _peers[senderIp] = DiscoveredPeer(
            ip: senderIp,
            name: name,
            os: os,
            deviceId: id,
            port: defaultTransferPort,
          );
        }
        notifyListeners();
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}
