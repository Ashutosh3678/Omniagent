import 'package:flutter/material.dart';

import '../mock_data.dart';
import '../widgets.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final TextEditingController _task;

  @override
  void initState() {
    super.initState();
    _task = TextEditingController(text: kDefaultTask);
  }

  @override
  void dispose() {
    _task.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
            child: StatusChip(label: kOfficePc.online ? 'Online' : 'Offline', selected: kOfficePc.online),
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
            onPressed: () {
              Navigator.of(context).pushNamed('/execution', arguments: _task.text.trim());
            },
            child: const Text('Run Task'),
          ),
          const SizedBox(height: 8),
          TaskTile(
            task: kHistory.first,
            onTap: () => Navigator.of(context).pushNamed('/result', arguments: kHistory.first),
          ),
          TaskTile(
            task: kHistory[1],
            onTap: () => Navigator.of(context).pushNamed('/result', arguments: kHistory[1]),
          ),
        ],
      ),
    );
  }
}
