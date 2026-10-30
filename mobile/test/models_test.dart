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

  test('steps carry their screenshot flag and problems are easy to spot', () {
    final task = TaskItem.fromJson({
      'status': 'partial',
      'steps': [
        {'name': 'Open Notepad', 'status': 'success', 'has_screenshot': true},
        {'name': 'Type "hi"', 'status': 'unverified', 'detail': 'could not confirm it on screen (best match 0.12)'},
        {'name': 'Press Enter', 'status': 'skipped'},
      ],
    });
    expect(task.steps.map((s) => s.hasScreenshot), [true, false, false]);
    expect(task.steps.map((s) => s.hasProblem), [false, true, false]);
  });

  test('a PC can browse only when its agent says so', () {
    expect(const PcDevice(name: 'a', hostName: 'h', online: true, actions: ['open_app']).canBrowse, isFalse);
    expect(const PcDevice(name: 'a', hostName: 'h', online: true, actions: ['browser_navigate']).canBrowse, isTrue);
  });
}
