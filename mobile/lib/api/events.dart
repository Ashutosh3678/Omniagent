import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models.dart';
import 'config.dart';
import 'session.dart';

/// The bits of a websocket the stream needs, so tests can stand in for a real one.
abstract class EventChannel {
  Stream<dynamic> get stream;
  Future<void> get ready;
  int? get closeCode;
  void send(String message);
  void close();
}

class _SocketChannel implements EventChannel {
  _SocketChannel(Uri uri) : _channel = WebSocketChannel.connect(uri);

  final WebSocketChannel _channel;

  @override
  Stream<dynamic> get stream => _channel.stream;
  @override
  Future<void> get ready => _channel.ready;
  @override
  int? get closeCode => _channel.closeCode;
  @override
  void send(String message) => _channel.sink.add(message);
  @override
  void close() => _channel.sink.close();
}

/// Close codes the backend uses.
const int kCloseUnauthorized = 4401;
const int kCloseTooManyConnections = 4429;

Duration defaultBackoff(int attempt) => Duration(seconds: (1 << attempt.clamp(0, 5)).clamp(1, 30));

/// Live task and PC updates pushed by the backend, kept connected for as long as the user is signed in.
///
/// Every event is a full snapshot, so a missed one costs nothing. After any (re)connect, and
/// whenever the backend says to, [resyncs] fires and screens reload what they show.
class EventStream {
  EventStream({
    Session? session,
    String? baseUrl,
    EventChannel Function(Uri uri)? connector,
    Duration Function(int attempt)? backoff,
    Duration? tooManyWait,
  })  : _session = session ?? appSession,
        _base = baseUrl ?? kApiBase,
        _connector = connector ?? _SocketChannel.new,
        _backoff = backoff ?? defaultBackoff,
        _tooManyWait = tooManyWait ?? const Duration(seconds: 30);

  final Session _session;
  final String _base;
  final EventChannel Function(Uri uri) _connector;
  final Duration Function(int attempt) _backoff;
  final Duration _tooManyWait;

  final _tasks = StreamController<TaskItem>.broadcast();
  final _agents = StreamController<PcDevice>.broadcast();
  final _resyncs = StreamController<void>.broadcast();

  /// True while the live connection is up. Screens poll slowly only when it is false.
  final ValueNotifier<bool> connected = ValueNotifier(false);

  Stream<TaskItem> get tasks => _tasks.stream;
  Stream<PcDevice> get agents => _agents.stream;
  Stream<void> get resyncs => _resyncs.stream;

  bool _running = false;
  int _generation = 0;
  EventChannel? _channel;

  Uri get _uri {
    final base = Uri.parse(_base);
    return base.replace(scheme: base.scheme == 'https' ? 'wss' : 'ws', path: '/api/v1/events');
  }

  void start() {
    if (_running) return;
    _running = true;
    _run(++_generation);
  }

  void stop() {
    _running = false;
    _generation++;
    _channel?.close();
    _channel = null;
    connected.value = false;
  }

  Future<void> _run(int generation) async {
    var attempt = 0;
    while (_running && generation == _generation) {
      final token = _session.token;
      if (token == null) {
        _running = false;
        break;
      }

      EventChannel? channel;
      try {
        channel = _connector(_uri);
        _channel = channel;
        await channel.ready;
        channel.send(jsonEncode({'type': 'auth', 'token': token}));
        await for (final raw in channel.stream) {
          if (!_running || generation != _generation) return;
          if (_handle(raw)) attempt = 0; // a good connection: next failure starts the waits over
        }
      } catch (_) {
        // Could not connect, or the connection broke: fall through and retry.
      }
      connected.value = false;
      final code = channel?.closeCode;
      if (code == kCloseUnauthorized) {
        // The login ran out or was revoked: back to the login screen.
        _running = false;
        await _session.signOut();
        return;
      }
      if (!_running || generation != _generation) return;
      await Future<void>.delayed(code == kCloseTooManyConnections ? _tooManyWait : _backoff(attempt++));
    }
  }

  /// Returns true for the hello that marks a working connection.
  bool _handle(dynamic raw) {
    final Map<String, dynamic> event;
    try {
      event = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return false;
    }
    try {
      switch (event['type']) {
        case 'hello':
          connected.value = true;
          _resyncs.add(null);
          return true;
        case 'resync':
          _resyncs.add(null);
        case 'task':
          _tasks.add(TaskItem.fromJson(event['task'] as Map<String, dynamic>, apiBase: _base));
        case 'agent':
          _agents.add(PcDevice.fromJson(event['agent'] as Map<String, dynamic>));
      }
    } catch (_) {
      // One malformed event must not take the stream down.
    }
    return false;
  }

  void dispose() {
    stop();
    _tasks.close();
    _agents.close();
    _resyncs.close();
  }
}

final events = EventStream();
