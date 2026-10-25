import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class LiveScreen extends StatefulWidget {
  const LiveScreen({super.key});

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> {
  Uint8List? _bytes;
  Timer? _poll;

  TaskItem? get _task {
    final args = ModalRoute.of(context)?.settings.arguments;
    return args is TaskItem ? args : null;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _poll ??= Timer.periodic(const Duration(seconds: 2), (_) => _load());
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final id = _task?.id;
    if (id == null) return;
    try {
      final bytes = await omniApi.getScreenshot(id);
      if (mounted && bytes != null) setState(() => _bytes = bytes);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final task = args is TaskItem ? args : TaskItem(title: args as String? ?? kDefaultTask, when: 'Now', status: TaskStatus.running);

    return Scaffold(
      appBar: AppBar(title: const Text('Live'), leading: const BackButton()),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(
          children: [
            Expanded(child: ScreenPreview(bytes: _bytes)),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () async {
                if (task.id != null) {
                  try {
                    final latest = await omniApi.getTask(task.id!);
                    if (!context.mounted) return;
                    Navigator.of(context).pushNamed('/result', arguments: latest);
                    return;
                  } catch (_) {}
                }
                if (!context.mounted) return;
                Navigator.of(context).pushNamed('/result', arguments: task);
              },
              child: const Text('Stop'),
            ),
          ],
        ),
      ),
    );
  }
}
