import 'package:flutter/material.dart';

import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class LiveScreen extends StatelessWidget {
  const LiveScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final task = ModalRoute.of(context)?.settings.arguments as String? ?? kDefaultTask;

    return Scaffold(
      appBar: AppBar(title: const Text('Live'), leading: const BackButton()),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(
          children: [
            const Expanded(child: ScreenPreview()),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () {
                Navigator.of(context).pushNamed(
                  '/result',
                  arguments: TaskItem(
                    title: task,
                    when: 'Now',
                    status: TaskStatus.success,
                    fileName: 'screenshot_190642.png',
                  ),
                );
              },
              child: const Text('Stop'),
            ),
          ],
        ),
      ),
    );
  }
}
