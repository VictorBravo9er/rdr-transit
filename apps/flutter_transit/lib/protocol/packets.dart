import 'dart:convert';
import 'dart:typed_data';

enum PacketType {
  header(1),
  data(2),
  finish(3),
  cancel(4),
  pause(5),
  resume(6),
  skip(7),
  query(8),
  queryResp(9),
  snippet(10);

  final int value;
  const PacketType(this.value);

  static PacketType? fromValue(int val) {
    for (final t in PacketType.values) {
      if (t.value == val) return t;
    }
    return null;
  }
}

class PacketHeader {
  final int payloadLength;
  final PacketType type;

  PacketHeader(this.payloadLength, this.type);
}

class LANProtocol {
  static const int headerStructSize = 5; // 4-byte int32 + 1-byte int8

  /// Create packet framing: 4-byte little-endian length + 1-byte type + payload
  static Uint8List framePacket(PacketType type, Uint8List payload) {
    final builder = BytesBuilder();
    final headerBytes = ByteData(5);
    headerBytes.setInt32(0, payload.length, Endian.little);
    headerBytes.setInt8(4, type.value);

    builder.add(headerBytes.buffer.asUint8List());
    if (payload.isNotEmpty) {
      builder.add(payload);
    }
    return builder.toBytes();
  }

  /// Create Header packet containing JSON file metadata
  static Uint8List createHeaderPacket({
    required String name,
    required String folder,
    required int size,
    String sha256 = '',
  }) {
    final map = <String, dynamic>{
      'name': name,
      'folder': folder,
      'size': size,
    };
    if (sha256.isNotEmpty) {
      map['sha256'] = sha256;
    }
    final jsonBytes = utf8.encode(jsonEncode(map));
    return framePacket(PacketType.header, Uint8List.fromList(jsonBytes));
  }

  /// Create Data packet containing file bytes
  static Uint8List createDataPacket(Uint8List chunk) {
    return framePacket(PacketType.data, chunk);
  }

  /// Create Finish packet
  static Uint8List createFinishPacket() {
    return framePacket(PacketType.finish, Uint8List(0));
  }

  /// Create Cancel packet
  static Uint8List createCancelPacket() {
    return framePacket(PacketType.cancel, Uint8List(0));
  }

  /// Create Skip packet
  static Uint8List createSkipPacket([String reason = 'already_exists']) {
    return framePacket(PacketType.skip, Uint8List.fromList(utf8.encode(reason)));
  }

  /// Create Snippet / clipboard packet
  static Uint8List createSnippetPacket(String text, [String sender = '']) {
    final map = {
      'text': text,
      'sender': sender,
    };
    final jsonBytes = utf8.encode(jsonEncode(map));
    return framePacket(PacketType.snippet, Uint8List.fromList(jsonBytes));
  }

  /// Parse Header packet JSON payload
  static Map<String, dynamic> parseHeaderPayload(Uint8List payload) {
    final str = utf8.decode(payload, allowMalformed: true);
    final decoded = jsonDecode(str);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    return {};
  }

  /// Parse packet header from 5-byte buffer
  static PacketHeader parsePacketHeader(Uint8List headerBuffer) {
    final byteData = ByteData.sublistView(headerBuffer);
    final len = byteData.getInt32(0, Endian.little);
    final typeVal = byteData.getInt8(4);
    final type = PacketType.fromValue(typeVal) ?? PacketType.data;
    return PacketHeader(len, type);
  }
}
