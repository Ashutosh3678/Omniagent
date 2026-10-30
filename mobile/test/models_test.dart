import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/api/client.dart';
import 'package:omniagent/api/session.dart';
import 'package:omniagent/widgets.dart';
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

  group('screenshots on the CDN', () {
    const cdn = 'https://res.cloudinary.com/democloud/image/authenticated/s--abc--/c_limit,q_auto,w_1080/v1/omniagent/u/t/final.png';

    test('a CDN address is used as it is; a backend path gets the backend address', () {
      expect(resolveUrl('http://api', cdn), cdn);
      expect(resolveUrl('http://api', '/api/v1/tasks/t1/screenshot'), 'http://api/api/v1/tasks/t1/screenshot');
      expect(resolveUrl('http://api', null), isNull);
      expect(resolveUrl('http://api', ''), isNull);
    });

    test('tasks and steps pick up their addresses and a clean file name', () {
      final task = TaskItem.fromJson({
        'status': 'completed',
        'screenshot_url': cdn,
        'steps': [
          {'name': 'Open', 'status': 'success', 'has_screenshot': true, 'screenshot_url': cdn.replaceAll('final', 'step-0')},
          {'name': 'Type', 'status': 'success'},
        ],
      }, apiBase: 'http://api');
      expect(task.screenshotUrl, cdn);
      expect(task.fileName, 'final.png');
      expect(task.steps[0].screenshotUrl, endsWith('/step-0.png'));
      expect(task.steps[1].screenshotUrl, isNull);
    });

    test('only our own backend addresses get the login header, never the CDN', () async {
      FlutterSecureStorage.setMockInitialValues({});
      final session = Session();
      await session.signIn(token: 'jwt', email: 'a@b.co', name: '');
      final api = OmniApi(session: session, baseUrl: 'http://api');
      expect(api.imageHeaders('http://api/api/v1/tasks/t1/screenshot'), {'Authorization': 'Bearer jwt'});
      expect(api.imageHeaders(cdn), isEmpty);
      expect(api.imageHeaders(null), isEmpty);
      await session.signOut();
      expect(api.imageHeaders('http://api/api/v1/tasks/t1/screenshot'), isEmpty);
    });

    testWidgets('the preview loads the CDN address and copes with a failure', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: Scaffold(body: ScreenPreview(height: 120, url: cdn))));
      final image = tester.widget<Image>(find.byType(Image));
      expect((image.image as NetworkImage).url, cdn);
      await tester.pumpAndSettle(); // the test environment has no network, so the image fails to load
      expect(find.text('Screenshot unavailable'), findsOneWidget);
    });
  });
}
