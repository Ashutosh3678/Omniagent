import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  static const _filters = ['All', 'Running', 'Success', 'Partial', 'Failed'];

  String _filter = 'All';
  List<TaskItem> _items = const [];
  bool _loaded = false;
  final List<StreamSubscription<dynamic>> _live = [];

  @override
  void initState() {
    super.initState();
    _load();
    _live.addAll([
      events.tasks.listen(_upsert),
      events.resyncs.listen((_) => _load()),
    ]);
  }

  @override
  void dispose() {
    for (final subscription in _live) {
      subscription.cancel();
    }
    super.dispose();
  }

  /// A task changed on the server: update it in place, or add it at the top if it is new.
  void _upsert(TaskItem task) {
    if (!mounted) return;
    setState(() {
      final index = _items.indexWhere((item) => item.id == task.id);
      _items = index >= 0
          ? [..._items.sublist(0, index), task, ..._items.sublist(index + 1)]
          : [task, ..._items];
    });
  }

  Future<void> _load() async {
    try {
      final tasks = await omniApi.listTasks();
      if (mounted) setState(() => _items = tasks);
    } catch (_) {
      // Keep whatever is already on screen.
    } finally {
      if (mounted) setState(() => _loaded = true);
    }
  }

  bool _matches(TaskItem task) => switch (_filter) {
        'Running' => task.status == TaskStatus.running || task.status == TaskStatus.pending,
        'Success' => task.status == TaskStatus.completed,
        'Partial' => task.status == TaskStatus.partial,
        'Failed' => task.status == TaskStatus.failed,
        _ => true,
      };

  @override
  Widget build(BuildContext context) {
    final items = _items.where(_matches).toList();

    return Scaffold(
      appBar: AppBar(title: const Text('History'), automaticallyImplyLeading: false),
      body: Column(
        children: [
          SizedBox(
            height: 48,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Gap.page, vertical: 4),
              itemCount: _filters.length,
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: (context, i) => FilterPill(
                label: _filters[i],
                selected: _filter == _filters[i],
                onTap: () => setState(() => _filter = _filters[i]),
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: !_loaded
                  ? const Center(child: CircularProgressIndicator())
                  : items.isEmpty
                      ? ListView(
                          children: [
                            EmptyState(
                              icon: Icons.history_rounded,
                              title: _items.isEmpty ? 'No tasks yet' : 'No ${_filter.toLowerCase()} tasks',
                              message: _items.isEmpty
                                  ? 'Tasks you run will show up here.'
                                  : 'Try a different filter.',
                            ),
                          ],
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, 24),
                          itemCount: items.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 10),
                          itemBuilder: (context, i) => TaskTile(
                            task: items[i],
                            onTap: () => Navigator.of(context).pushNamed('/result', arguments: items[i]),
                          ),
                        ),
            ),
          ),
        ],
      ),
    );
  }
}
