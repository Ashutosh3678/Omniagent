import 'dart:async';
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class LiveScreen extends StatefulWidget {
  const LiveScreen({super.key});

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> {
  String? _url;
  String _caption = '';
  Timer? _poll;

  TaskItem? get _task {
    final args = ModalRoute.of(context)?.settings.arguments;
    return args is TaskItem ? args : null;
  }

  StreamSubscription<TaskItem>? _live;
  StreamSubscription<void>? _resync;
  int _shown = -1;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_poll == null) {
      final id = _task?.id;
      // A new screenshot or a finished task is pushed; this slow check only covers a dropped connection.
      _poll = Timer.periodic(const Duration(seconds: 5), (_) {
        if (!events.connected.value) _load();
      });
      _live = events.tasks.where((task) => task.id == id).listen(_apply);
      _resync = events.resyncs.listen((_) => _load());
      _load();
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    _live?.cancel();
    _resync?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final id = _task?.id;
    if (id == null) return;
    try {
      _apply(await omniApi.getTask(id));
    } catch (_) {}
  }

  /// Shows the newest step thumbnail, or the final screenshot once there is one. The addresses come
  /// with the task, so no extra request is needed.
  void _apply(TaskItem task) {
    if (!mounted) return;
    final index = task.steps.lastIndexWhere((step) => step.screenshotUrl != null);
    final url = index >= 0 ? task.steps[index].screenshotUrl : task.screenshotUrl;
    if (url == null || (url == _url && index == _shown)) return;
    setState(() {
      _url = url;
      _caption = index >= 0 ? task.steps[index].name : '';
      _shown = index;
    });
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
            Expanded(child: ScreenPreview(url: _url, headers: omniApi.imageHeaders(_url))),
            if (_caption.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('After: $_caption', style: Theme.of(context).textTheme.bodySmall),
            ],
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
