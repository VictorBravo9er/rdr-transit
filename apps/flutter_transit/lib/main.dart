import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'services/discovery_service.dart';
import 'services/transfer_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const RDRTransitApp());
}

class RDRTransitApp extends StatelessWidget {
  const RDRTransitApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RDR Transit',
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.dark,
      darkTheme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00E5FF),
          secondary: Color(0xFF00E676),
          surface: Color(0xFF161B22),
        ),
        cardTheme: const CardThemeData(
          color: Color(0xFF1C2128),
          elevation: 2,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF161B22),
          elevation: 0,
        ),
      ),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  final DiscoveryService _discoveryService = DiscoveryService();
  final TransferService _transferService = TransferService();

  // Staged files for sending
  final List<PlatformFile> _stagedFiles = [];
  final TextEditingController _snippetController = TextEditingController();
  final TextEditingController _directIpController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _initServices();
  }

  Future<void> _initServices() async {
    await _transferService.init();
    await _discoveryService.start();
    await _transferService.startReceiver();

    _discoveryService.addListener(() => setState(() {}));
    _transferService.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _discoveryService.dispose();
    _transferService.dispose();
    _snippetController.dispose();
    _directIpController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('⚡ RDR Transit', style: TextStyle(fontWeight: FontWeight.bold)),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: _transferService.isReceiving
                    ? Colors.green.withValues(alpha: 0.2)
                    : Colors.red.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: _transferService.isReceiving ? Colors.green : Colors.red,
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.circle,
                    size: 8,
                    color: _transferService.isReceiving ? Colors.greenAccent : Colors.redAccent,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    _transferService.isReceiving ? 'Receiver On' : 'Receiver Off',
                    style: TextStyle(
                      fontSize: 12,
                      color: _transferService.isReceiving ? Colors.greenAccent : Colors.redAccent,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: [
          _buildPeersTab(),
          _buildSendTab(),
          _buildReceiveTab(),
          _buildSnippetTab(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (idx) => setState(() => _currentIndex = idx),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.wifi_tethering), label: 'Peers'),
          NavigationDestination(icon: Icon(Icons.send_rounded), label: 'Send'),
          NavigationDestination(icon: Icon(Icons.download_rounded), label: 'Receive'),
          NavigationDestination(icon: Icon(Icons.copy_rounded), label: 'Snippet'),
        ],
      ),
    );
  }

  // --- TAB 1: PEERS ---
  Widget _buildPeersTab() {
    final peers = _discoveryService.peers;
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          color: const Color(0xFF161B22),
          child: Row(
            children: [
              Text(
                'Nearby Devices (${peers.length})',
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const Spacer(),
              ElevatedButton.icon(
                onPressed: () {
                  _discoveryService.triggerBeacon();
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Broadcasting discovery beacon...'), duration: Duration(seconds: 1)),
                  );
                },
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Scan'),
              ),
            ],
          ),
        ),
        Expanded(
          child: peers.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.wifi_find, size: 64, color: Colors.grey),
                      SizedBox(height: 12),
                      Text('Searching for LAN-Share / RDR Transit peers...', style: TextStyle(color: Colors.grey)),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: peers.length,
                  itemBuilder: (ctx, i) {
                    final peer = peers[i];
                    return Card(
                      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor: const Color(0xFF00E5FF).withValues(alpha: 0.15),
                          child: Icon(
                            peer.osBadge == 'Apple'
                                ? Icons.apple
                                : peer.osBadge == 'Android'
                                    ? Icons.android
                                    : peer.osBadge == 'Windows'
                                        ? Icons.window
                                        : Icons.computer,
                            color: const Color(0xFF00E5FF),
                          ),
                        ),
                        title: Text(peer.name, style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Text('${peer.ip}:${peer.port} • ${peer.osBadge}'),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.send_rounded, color: Color(0xFF00E5FF)),
                              tooltip: 'Send Files',
                              onPressed: () {
                                setState(() {
                                  _directIpController.text = peer.ip;
                                  _currentIndex = 1;
                                });
                              },
                            ),
                            IconButton(
                              icon: const Icon(Icons.copy_rounded, color: Color(0xFF00E676)),
                              tooltip: 'Send Snippet',
                              onPressed: () {
                                setState(() {
                                  _directIpController.text = peer.ip;
                                  _currentIndex = 3;
                                });
                              },
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  // --- TAB 2: SEND ---
  Widget _buildSendTab() {
    final progress = _transferService.currentProgress;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Target Peer field
          TextField(
            controller: _directIpController,
            decoration: InputDecoration(
              labelText: 'Target Peer IP',
              hintText: 'e.g. 192.168.1.150',
              prefixIcon: const Icon(Icons.lan_rounded),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              suffixIcon: _discoveryService.peers.isNotEmpty
                  ? PopupMenuButton<String>(
                      icon: const Icon(Icons.arrow_drop_down),
                      onSelected: (ip) {
                        setState(() {
                          _directIpController.text = ip;
                        });
                      },
                      itemBuilder: (ctx) => _discoveryService.peers
                          .map((p) => PopupMenuItem(value: p.ip, child: Text('${p.name} (${p.ip})')))
                          .toList(),
                    )
                  : null,
            ),
          ),
          const SizedBox(height: 12),

          // File Staging area
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _pickFiles,
                  icon: const Icon(Icons.note_add_rounded),
                  label: const Text('Add Files'),
                ),
              ),
              const SizedBox(width: 10),
              IconButton(
                onPressed: () => setState(() => _stagedFiles.clear()),
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Clear List',
              ),
            ],
          ),
          const SizedBox(height: 8),

          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF161B22),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.white12),
              ),
              child: _stagedFiles.isEmpty
                  ? const Center(child: Text('No files staged yet.', style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      itemCount: _stagedFiles.length,
                      itemBuilder: (ctx, i) {
                        final f = _stagedFiles[i];
                        return ListTile(
                          dense: true,
                          title: Text(f.name, overflow: TextOverflow.ellipsis),
                          subtitle: Text(_formatBytes(f.size)),
                          trailing: IconButton(
                            icon: const Icon(Icons.close, size: 18),
                            onPressed: () => setState(() => _stagedFiles.removeAt(i)),
                          ),
                        );
                      },
                    ),
            ),
          ),
          const SizedBox(height: 12),

          // Live Progress
          if (progress != null) ...[
            LinearProgressIndicator(value: progress.percent),
            const SizedBox(height: 6),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    progress.isComplete ? 'Transfer Completed!' : 'Sending: ${progress.fileName}',
                    style: const TextStyle(fontSize: 12),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  '${(progress.percent * 100).toStringAsFixed(1)}% (${progress.speedMbPerSec.toStringAsFixed(2)} MB/s)',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 12),
          ],

          // Send Action Button
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF00E5FF),
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            onPressed: _startSendingFiles,
            icon: const Icon(Icons.bolt_rounded),
            label: Text(
              'Send ${_stagedFiles.length} File(s)',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ),
        ],
      ),
    );
  }

  // --- TAB 3: RECEIVE ---
  Widget _buildReceiveTab() {
    final history = _transferService.history;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Receiver Daemon', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                        const SizedBox(height: 4),
                        Text(
                          _transferService.isReceiving
                              ? 'Listening on TCP port 17116'
                              : 'Stopped (not accepting transfers)',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  Switch(
                    value: _transferService.isReceiving,
                    onChanged: (on) {
                      if (on) {
                        _transferService.startReceiver();
                      } else {
                        _transferService.stopReceiver();
                      }
                    },
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Text('Received Files & Items', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),

          Expanded(
            child: history.isEmpty
                ? const Center(child: Text('No files received yet.', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: history.length,
                    itemBuilder: (ctx, i) {
                      final item = history[i];
                      return Card(
                        child: ListTile(
                          leading: Icon(
                            item.isSnippet ? Icons.content_paste_rounded : Icons.insert_drive_file_rounded,
                            color: item.isSnippet ? Colors.amberAccent : Colors.greenAccent,
                          ),
                          title: Text(item.fileName, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            item.isSnippet
                                ? item.snippetText
                                : '${_formatBytes(item.size)} • from ${item.senderIp}',
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  // --- TAB 4: SNIPPET ---
  Widget _buildSnippetTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _directIpController,
                  decoration: const InputDecoration(
                    labelText: 'Target IP',
                    hintText: '192.168.1.xxx',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.paste_rounded),
                tooltip: 'Paste from Clipboard',
                onPressed: () async {
                  final data = await Clipboard.getData('text/plain');
                  if (data?.text != null) {
                    _snippetController.text = data!.text!;
                  }
                },
              ),
            ],
          ),
          const SizedBox(height: 12),
          Expanded(
            child: TextField(
              controller: _snippetController,
              maxLines: null,
              expands: true,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Type or paste snippet text here...',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF00E676),
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            onPressed: _sendSnippet,
            icon: const Icon(Icons.send_rounded),
            label: const Text('Send Snippet to Device', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  // --- ACTIONS ---
  Future<void> _pickFiles() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true);
    if (result != null) {
      setState(() {
        _stagedFiles.addAll(result.files);
      });
    }
  }

  Future<void> _startSendingFiles() async {
    final target = _directIpController.text.trim();
    if (target.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please enter or select a target IP.')));
      return;
    }
    if (_stagedFiles.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please add at least one file.')));
      return;
    }

    for (final file in _stagedFiles) {
      if (file.path != null) {
        await _transferService.sendFile(targetIp: target, filePath: file.path!);
      }
    }

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Finished sending files!')));
  }

  Future<void> _sendSnippet() async {
    final target = _directIpController.text.trim();
    final text = _snippetController.text.trim();
    if (target.isEmpty || text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Target IP and text required.')));
      return;
    }

    final ok = await _transferService.sendSnippet(targetIp: target, text: text);
    if (!mounted) return;
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Snippet sent successfully!')));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to send snippet.')));
    }
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  }
}
