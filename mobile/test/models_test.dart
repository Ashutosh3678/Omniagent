import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/models.dart';

void main() {
  test('partial task keeps its held-back steps and details', () {
    final task = TaskItem.fromJson({
      'id': 't1',
      'instruction': 'open notepad and type hi',
      'status': 'partial',
      'summary': 'Completed 1 of 1 step(s)',
      'error': '',
      'steps': [
        {'name': 'Open Notepad', 'status': 'success', 'detail': ''},
        {'name': 'Click', 'status': 'held_back', 'detail': 'click is not available on this PC yet'},
      ],
    });

    expect(task.status, TaskStatus.partial);
    expect(task.statusLabel, 'Partial');
    expect(task.steps.map((s) => s.status), ['success', 'held_back']);
    expect(task.steps[1].detail, contains('not available'));
  });

  test('unknown status falls back to pending', () {
    expect(TaskItem.fromJson({'status': 'weird'}).status, TaskStatus.pending);
  });
}
