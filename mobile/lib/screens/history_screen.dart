import 'package:flutter/material.dart';

import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  String _filter = 'All';

  @override
  Widget build(BuildContext context) {
    final items = kHistory.where((task) {
      if (_filter == 'Success') return task.status == TaskStatus.success;
      if (_filter == 'Failed') return task.status == TaskStatus.failed;
      return true;
    }).toList();

    return Scaffold(
      appBar: AppBar(title: const Text('History'), automaticallyImplyLeading: false),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
            child: Row(
              children: [
                for (final label in const ['All', 'Success', 'Failed']) ...[
                  StatusChip(
                    label: label,
                    selected: _filter == label,
                    onTap: () => setState(() => _filter = label),
                  ),
                  const SizedBox(width: 8),
                ],
              ],
            ),
          ),
          Expanded(
            child: ListView(
              children: [
                for (final task in items)
                  TaskTile(
                    task: task,
                    onTap: () => Navigator.of(context).pushNamed('/result', arguments: task),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
