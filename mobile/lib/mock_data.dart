import 'models.dart';

const String kDefaultTask = 'Open Notepad and type Hello from OmniAgent';

const List<TaskItem> kHistory = [
  TaskItem(title: 'Open Notepad', when: 'Today', status: TaskStatus.completed, fileName: 'screenshot_190642.png'),
  TaskItem(title: 'Screenshot desktop', when: 'Yesterday', status: TaskStatus.failed),
  TaskItem(title: 'Type message', when: 'Oct 24', status: TaskStatus.completed),
  TaskItem(title: 'Close Chrome', when: 'Oct 23', status: TaskStatus.completed),
];

const List<String> kExecutionSteps = [
  'Open Notepad',
  'Type message',
  'Screenshot',
  'Verify',
];
