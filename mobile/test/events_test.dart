import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/api/events.dart';
import 'package:omniagent/api/session.dart';
import 'package:omniagent/models.dart';

class FakeChannel implements EventChannel {
  final incoming = StreamController<dynamic>();
  final sent = <String>[];
  bool closed = false;
  @override
  int? closeCode;

  @override
  Stream<dynamic> get stream => incoming.stream;
  @override
  Future<void> get ready async {}
  @override
  void send(String message) => sent.add(message);
  @override
  void close() => closed = true;

  void push(Map<String, dynamic> event) => incoming.add(jsonEncode(event));
  Future<void> drop([int? code]) async {
    closeCode = code;
    await incoming.close();
  }
}

Future<void> until(bool Function() condition, {int ms = 2000}) async {
  final end = DateTime.now().add(Duration(milliseconds: ms));
  while (!condition()) {
    if (DateTime.now().isAfter(end)) fail('condition not met in time');
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}

Map<String, dynamic> taskJson(String id, String status, {List<Map<String, dynamic>> steps = const []}) => {
      'id': id,
      'instruction': 'open notepad',
      'status': status,
      'steps': steps,
      'summary': '',
      'error': '',
    };

void main() {
  late Session session;
  late List<FakeChannel> channels;
  late List<Uri> uris;

  EventStream make({Duration Function(int)? backoff, Duration? tooManyWait}) => EventStream(
        session: session,
        baseUrl: 'http://10.0.2.2:8000',
        backoff: backoff ?? (_) => const Duration(milliseconds: 10),
        tooManyWait: tooManyWait ?? const Duration(milliseconds: 80),
        connector: (uri) {
          uris.add(uri);
          final channel = FakeChannel();
          channels.add(channel);
          return channel;
        },
      );

  setUp(() async {
    FlutterSecureStorage.setMockInitialValues({});
    session = Session();
    await session.signIn(token: 'jwt-token', email: 'a@b.co', name: '');
    channels = [];
    uris = [];
  });

  test('connects to the events address and logs in with the first message, never in the URL', () async {
    final stream = make()..start();
    await until(() => channels.isNotEmpty && channels.first.sent.isNotEmpty);
    expect(uris.first.toString(), 'ws://10.0.2.2:8000/api/v1/events');
    expect(uris.first.toString(), isNot(contains('jwt-token')));
    expect(jsonDecode(channels.first.sent.first), {'type': 'auth', 'token': 'jwt-token'});
    stream.dispose();
  });

  test('https becomes wss', () async {
    final stream = EventStream(
      session: session,
      baseUrl: 'https://api.example.com',
      connector: (uri) {
        uris.add(uri);
        return FakeChannel();
      },
    )..start();
    await until(() => uris.isNotEmpty);
    expect(uris.first.toString(), 'wss://api.example.com/api/v1/events');
    stream.dispose();
  });

  test('hello marks it connected and asks screens to reload', () async {
    final stream = make()..start();
    var resyncs = 0;
    stream.resyncs.listen((_) => resyncs++);
    await until(() => channels.isNotEmpty);
    expect(stream.connected.value, isFalse);
    channels.first.push({'type': 'hello'});
    await until(() => stream.connected.value);
    await until(() => resyncs == 1);
    stream.dispose();
  });

  test('task and PC snapshots are delivered as models; junk is ignored', () async {
    final stream = make()..start();
    final tasks = <TaskItem>[];
    final agents = <PcDevice>[];
    stream.tasks.listen(tasks.add);
    stream.agents.listen(agents.add);
    await until(() => channels.isNotEmpty);
    final channel = channels.first;
    channel.push({'type': 'hello'});
    channel.incoming.add('not json');
    channel.incoming.add(jsonEncode({'type': 'task', 'task': 'broken'}));
    channel.push({'type': 'unknown'});
    channel.push({
      'type': 'task',
      'task': taskJson('t1', 'running', steps: [
        {'name': 'Open Notepad', 'status': 'success', 'detail': '', 'has_screenshot': true},
      ]),
    });
    channel.push({
      'type': 'agent',
      'agent': {'id': 'a1', 'name': 'Office PC', 'hostname': 'H', 'online': true, 'status': 'active', 'permitted_apps': ['notepad'], 'actions': ['open_app']},
    });
    await until(() => tasks.isNotEmpty && agents.isNotEmpty);
    expect(tasks.single.id, 't1');
    expect(tasks.single.status, TaskStatus.running);
    expect(tasks.single.steps.single.hasScreenshot, isTrue);
    expect(agents.single.online, isTrue);
    expect(agents.single.name, 'Office PC');
    stream.dispose();
  });

  test('a resync event reaches the screens', () async {
    final stream = make()..start();
    var resyncs = 0;
    stream.resyncs.listen((_) => resyncs++);
    await until(() => channels.isNotEmpty);
    channels.first.push({'type': 'resync'});
    await until(() => resyncs == 1);
    stream.dispose();
  });

  test('a dropped connection is re-opened, logs in again and resyncs', () async {
    final stream = make()..start();
    var resyncs = 0;
    stream.resyncs.listen((_) => resyncs++);
    await until(() => channels.isNotEmpty);
    channels.first.push({'type': 'hello'});
    await until(() => stream.connected.value);

    await channels.first.drop();
    await until(() => !stream.connected.value);
    await until(() => channels.length == 2 && channels[1].sent.isNotEmpty);
    expect(jsonDecode(channels[1].sent.first)['token'], 'jwt-token');
    channels[1].push({'type': 'hello'});
    await until(() => stream.connected.value);
    expect(resyncs, 2); // once per successful connection
    stream.dispose();
  });

  test('waits grow while the server is unreachable and start over after a good connection', () async {
    final asked = <int>[];
    final stream = make(backoff: (attempt) {
      asked.add(attempt);
      return const Duration(milliseconds: 5);
    })
      ..start();
    for (var i = 0; i < 3; i++) {
      await until(() => channels.length == i + 1);
      await channels[i].drop();
    }
    await until(() => channels.length == 4);
    channels[3].push({'type': 'hello'});
    await until(() => stream.connected.value);
    await channels[3].drop();
    await until(() => channels.length == 5);
    expect(asked.take(3), [0, 1, 2]);
    expect(asked[3], 0); // reset by the successful hello
    stream.dispose();
  });

  test('default waits grow and are capped', () {
    expect([for (var i = 0; i < 8; i++) defaultBackoff(i).inSeconds], [1, 2, 4, 8, 16, 30, 30, 30]);
  });

  test('an expired login signs the user out and stops retrying', () async {
    final stream = make()..start();
    await until(() => channels.isNotEmpty);
    await channels.first.drop(kCloseUnauthorized);
    await until(() => !session.isSignedIn);
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(channels.length, 1);
    stream.dispose();
  });

  test('too many open connections waits longer before trying again', () async {
    final stream = make(tooManyWait: const Duration(milliseconds: 200))..start();
    await until(() => channels.isNotEmpty);
    final dropped = DateTime.now();
    await channels.first.drop(kCloseTooManyConnections);
    await until(() => channels.length == 2);
    expect(DateTime.now().difference(dropped).inMilliseconds, greaterThanOrEqualTo(180));
    stream.dispose();
  });

  test('stop closes the connection and does not reconnect', () async {
    final stream = make()..start();
    await until(() => channels.isNotEmpty);
    channels.first.push({'type': 'hello'});
    await until(() => stream.connected.value);
    stream.stop();
    expect(channels.first.closed, isTrue);
    expect(stream.connected.value, isFalse);
    await channels.first.drop();
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(channels.length, 1);
    stream.dispose();
  });

  test('it can be started again after a stop (sign in again)', () async {
    final stream = make()..start();
    await until(() => channels.length == 1);
    stream.stop();
    await channels.first.drop();
    stream.start();
    await until(() => channels.length == 2);
    stream.dispose();
  });

  test('without a login it does not connect at all', () async {
    await session.signOut();
    final stream = make()..start();
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(channels, isEmpty);
    stream.dispose();
  });
}
