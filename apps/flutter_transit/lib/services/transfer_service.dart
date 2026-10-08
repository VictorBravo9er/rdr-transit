import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import '../protocol/packets.dart';

class FileTransferProgress {
  final String fileName;
  final int totalBytes;
  final int sentBytes;
  final double speedMbPerSec;
  final bool isComplete;
  final String? error;

  FileTransferProgress({
    required this.fileName,
    required this.totalBytes,
    required this.sentBytes,
    required this.speedMbPerSec,
    this.isComplete = false,
    this.error,
  });

  double get percent => totalBytes > 0 ? (sentBytes / totalBytes).clamp(0.0, 1.0) : 0.0;
}

class ReceivedItem {
  final String fileName;
  final String filePath;
  final int size;
  final String senderIp;
  final DateTime time;
  final bool isSnippet;
  final String snippetText;

  ReceivedItem({
    required this.fileName,
    required this.filePath,
    required this.size,
    required this.senderIp,
    DateTime? time,
    this.isSnippet = false,
    this.snippetText = '',
  }) : time = time ?? DateTime.now();
}

class TransferService extends ChangeNotifier {
  static const int chunkSize = 98304; // 96 KB
  static const int defaultPort = 17116;

  ServerSocket? _serverSocket;
  bool _isReceiving = false;
  FileTransferProgress? _currentProgress;
  final List<ReceivedItem> _history = [];
  String _downloadDirectory = '';

  bool get isReceiving => _isReceiving;
  FileTransferProgress? get currentProgress => _currentProgress;
  List<ReceivedItem> get history => List.unmodifiable(_history.reversed);

  Future<void> init() async {
    Directory? dir;
    if (Platform.isAndroid || Platform.isIOS) {
      dir = await getApplicationDocumentsDirectory();
    } else {
      dir = await getDownloadsDirectory() ?? await getApplicationDocumentsDirectory();
    }
    _downloadDirectory = dir.path;
  }

  Future<void> startReceiver({int port = defaultPort}) async {
    if (_isReceiving) return;
    if (_downloadDirectory.isEmpty) await init();

    try {
      _serverSocket = await ServerSocket.bind(InternetAddress.anyIPv4, port, shared: true);
      _isReceiving = true;
      _serverSocket?.listen(_handleIncomingClient);
      notifyListeners();
    } catch (e) {
      debugPrint('Receiver bind error: $e');
    }
  }

  void stopReceiver() {
    _serverSocket?.close();
    _serverSocket = null;
    _isReceiving = false;
    notifyListeners();
  }

  void _handleIncomingClient(Socket client) async {
    final senderIp = client.remoteAddress.address;
    IOSink? currentFileWriter;
    String? currentFileName;
    String? currentFilePath;
    int expectedBytes = 0;
    int receivedBytes = 0;

    final streamConsumer = Completer<void>();
    final buffer = BytesBuilder();

    client.listen(
      (data) async {
        buffer.add(data);

        while (true) {
          final currentBytes = buffer.toBytes();
          if (currentBytes.length < LANProtocol.headerStructSize) {
            break; // Wait for full 5-byte header
          }

          final header = LANProtocol.parsePacketHeader(Uint8List.sublistView(currentBytes, 0, 5));
          final totalPacketLen = LANProtocol.headerStructSize + header.payloadLength;

          if (currentBytes.length < totalPacketLen) {
            break; // Wait for remaining payload
          }

          final payload = Uint8List.sublistView(currentBytes, 5, totalPacketLen);
          // Consume packet from buffer
          final remaining = Uint8List.sublistView(currentBytes, totalPacketLen);
          buffer.clear();
          buffer.add(remaining);

          // Handle packet types
          if (header.type == PacketType.header) {
            final metadata = LANProtocol.parseHeaderPayload(payload);
            currentFileName = metadata['name'] as String? ?? 'received_file';
            expectedBytes = (metadata['size'] as num?)?.toInt() ?? 0;
            final folder = metadata['folder'] as String? ?? '';

            var targetDir = Directory(_downloadDirectory);
            if (folder.isNotEmpty) {
              targetDir = Directory('${targetDir.path}/$folder');
              if (!targetDir.existsSync()) targetDir.createSync(recursive: true);
            }
            final targetFile = File('${targetDir.path}/$currentFileName');
            currentFilePath = targetFile.path;
            currentFileWriter = targetFile.openWrite();
            receivedBytes = 0;
          } else if (header.type == PacketType.data) {
            currentFileWriter?.add(payload);
            receivedBytes += payload.length;
          } else if (header.type == PacketType.finish) {
            await currentFileWriter?.flush();
            await currentFileWriter?.close();
            currentFileWriter = null;

            if (currentFileName != null && currentFilePath != null) {
              _history.add(ReceivedItem(
                fileName: currentFileName!,
                filePath: currentFilePath!,
                size: receivedBytes > 0 ? receivedBytes : expectedBytes,
                senderIp: senderIp,
              ));
              notifyListeners();
            }
            // Send finish ACK back to sender
            client.add(LANProtocol.createFinishPacket());
            await client.flush();
            client.destroy();
            break;
          } else if (header.type == PacketType.snippet) {
            final metadata = LANProtocol.parseHeaderPayload(payload);
            final text = metadata['text'] as String? ?? '';
            _history.add(ReceivedItem(
              fileName: 'Snippet from $senderIp',
              filePath: '',
              size: text.length,
              senderIp: senderIp,
              isSnippet: true,
              snippetText: text,
            ));
            notifyListeners();
            client.destroy();
            break;
          }
        }
      },
      onError: (err) {
        currentFileWriter?.close();
        client.destroy();
      },
      onDone: () {
        currentFileWriter?.close();
        if (!streamConsumer.isCompleted) streamConsumer.complete();
      },
    );
  }

  /// Send a single file to a target IP
  Future<bool> sendFile({
    required String targetIp,
    required String filePath,
    int port = defaultPort,
  }) async {
    final file = File(filePath);
    if (!file.existsSync()) return false;

    final fileName = file.uri.pathSegments.last;
    final totalBytes = file.lengthSync();
    int sentBytes = 0;
    final startTime = DateTime.now();

    try {
      final socket = await Socket.connect(targetIp, port, timeout: const Duration(seconds: 8));

      // 1. Send Header packet
      final headerPacket = LANProtocol.createHeaderPacket(name: fileName, folder: '', size: totalBytes);
      socket.add(headerPacket);
      await socket.flush();

      // 2. Stream Data packets
      final fileStream = file.openRead();
      await for (final chunk in fileStream) {
        final dataPacket = LANProtocol.createDataPacket(Uint8List.fromList(chunk));
        socket.add(dataPacket);
        sentBytes += chunk.length;

        final elapsedSec = maxDouble(0.001, DateTime.now().difference(startTime).inMilliseconds / 1000.0);
        final speedMb = (sentBytes / (1024 * 1024)) / elapsedSec;

        _currentProgress = FileTransferProgress(
          fileName: fileName,
          totalBytes: totalBytes,
          sentBytes: sentBytes,
          speedMbPerSec: speedMb,
        );
        notifyListeners();
      }

      // 3. Send Finish packet
      socket.add(LANProtocol.createFinishPacket());
      await socket.flush();

      _currentProgress = FileTransferProgress(
        fileName: fileName,
        totalBytes: totalBytes,
        sentBytes: totalBytes,
        speedMbPerSec: 0.0,
        isComplete: true,
      );
      notifyListeners();

      await socket.close();
      return true;
    } catch (e) {
      _currentProgress = FileTransferProgress(
        fileName: fileName,
        totalBytes: totalBytes,
        sentBytes: sentBytes,
        speedMbPerSec: 0.0,
        error: e.toString(),
      );
      notifyListeners();
      return false;
    }
  }

  /// Send text / snippet to target IP
  Future<bool> sendSnippet({
    required String targetIp,
    required String text,
    int port = defaultPort,
    String senderName = '',
  }) async {
    try {
      final socket = await Socket.connect(targetIp, port, timeout: const Duration(seconds: 6));
      final pkt = LANProtocol.createSnippetPacket(text, senderName);
      socket.add(pkt);
      await socket.flush();
      await socket.close();
      return true;
    } catch (e) {
      debugPrint('Snippet send error: $e');
      return false;
    }
  }

  double maxDouble(double a, double b) => a > b ? a : b;
}
