import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../models.dart';
import '../theme.dart';
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
  StreamSubscription<TaskItem>? _live;
  StreamSubscription<void>? _resync;
  int _shown = -1;

  TaskItem? get _task {
    final args = ModalRoute.of(context)?.settings.arguments;
    return args is TaskItem ? args : null;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_poll != null) return;
    final id = _task?.id;
    // A new screenshot or a finished task is pushed; this slow check only covers a dropped connection.
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!events.connected.value) _load();
    });
    _live = events.tasks.where((task) => task.id == id).listen(_apply);
    _resync = events.resyncs.listen((_) => _load());
    _apply(_task);
    _load();
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
  void _apply(TaskItem? task) {
    if (!mounted || task == null) return;
    final index = task.steps.lastIndexWhere((step) => step.screenshotUrl != null);
    final url = index >= 0 ? task.steps[index].screenshotUrl : task.screenshotUrl;
    if (url == null || (url == _url && index == _shown)) return;
    setState(() {
      _url = url;
      _caption = index >= 0 ? task.steps[index].name : '';
      _shown = index;
    });
  }

  Future<void> _openResult() async {
    final task = _task;
    if (task == null) return;
    var latest = task;
    if (task.id != null) {
      try {
        latest = await omniApi.getTask(task.id!);
      } catch (_) {}
    }
    if (!mounted) return;
    Navigator.of(context).pushNamed('/result', arguments: latest);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Live view')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, Gap.page),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: ScreenPreview(url: _url, headers: omniApi.imageHeaders(_url))),
              if (_caption.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(
                  'After: $_caption',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                ),
              ],
              const SizedBox(height: 16),
              OutlinedButton(onPressed: _openResult, child: const Text('View result')),
            ],
          ),
        ),
      ),
    );
  }
}
