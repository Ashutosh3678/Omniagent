import 'package:flutter/material.dart';

import '../api/client.dart';
import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final TextEditingController _task;
  List<PcDevice> _agents = const [];
  List<TaskItem> _recent = const [];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _task = TextEditingController(text: kDefaultTask);
    _refresh();
  }

  @override
  void dispose() {
    _task.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final agents = await omniApi.listAgents();
      final tasks = await omniApi.listTasks();
      if (!mounted) return;
      setState(() {
        _agents = agents;
        _recent = tasks.take(2).toList();
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _agents = const [];
        _recent = const [];
      });
    }
  }

  PcDevice? get _device {
    for (final agent in _agents) {
      if (agent.online) return agent;
    }
    return _agents.isEmpty ? null : _agents.first;
  }

  Future<void> _runTask() async {
    final instruction = _task.text.trim();
    if (instruction.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      final task = await omniApi.createTask(instruction, agentId: _device?.id);
      if (!mounted) return;
      await Navigator.of(context).pushNamed('/execution', arguments: task);
      await _refresh();
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      await _refresh();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final online = _device?.online ?? false;
    final recent = _recent.isEmpty ? kHistory.take(2).toList() : _recent;

    return Scaffold(
      appBar: AppBar(
        title: const Text('OmniAgent'),
        automaticallyImplyLeading: false,
        actions: const [
          Padding(
            padding: EdgeInsets.only(right: 16),
            child: CircleAvatar(radius: 16, child: Icon(Icons.person, size: 18)),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: StatusChip(label: online ? 'Online' : 'Offline', selected: online),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _task,
            minLines: 3,
            maxLines: 5,
            decoration: const InputDecoration(labelText: 'Task'),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _runTask,
            child: Text(_busy ? 'Starting' : 'Run Task'),
          ),
          const SizedBox(height: 8),
          for (final task in recent)
            TaskTile(
              task: task,
              onTap: () => Navigator.of(context).pushNamed('/result', arguments: task),
            ),
        ],
      ),
    );
  }
}
