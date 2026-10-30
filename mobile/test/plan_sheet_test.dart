import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/models.dart';
import 'package:omniagent/screens/plan_sheet.dart';

PlanPreview preview(Map<String, dynamic> overrides) => PlanPreview.fromJson({
      'planner': 'gemini',
      'steps': [
        {'description': 'Open Notepad', 'confidence': 0.9},
        {'description': 'Type "Hi"', 'confidence': 0.9},
      ],
      'held_back': [],
      'runnable': true,
      'low_confidence': false,
      'note': '',
      'confidence': 0.9,
      'plan': [
        {'action': {'type': 'open_app', 'app': 'notepad'}},
      ],
      ...overrides,
    });

Future<bool?> openSheet(WidgetTester tester, PlanPreview p) async {
  bool? result;
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () async => result = await showPlanSheet(context, p),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return result;
}

void main() {
  test('preview parses steps, held-back steps and the raw plan', () {
    final p = preview({
      'held_back': [
        {'reason': 'not_supported', 'detail': 'click is not available on this PC yet'}
      ],
      'low_confidence': true,
    });
    expect(p.steps.map((s) => s.description), ['Open Notepad', 'Type "Hi"']);
    expect(p.heldBack.single.reason, 'not_supported');
    expect(p.lowConfidence, isTrue);
    expect(p.plan, hasLength(1));
  });

  testWidgets('sheet lists the steps and confirms with Run', (tester) async {
    await openSheet(tester, preview({}));
    expect(find.text('Here is the plan'), findsOneWidget);
    expect(find.text('Open Notepad'), findsOneWidget);
    expect(find.text('Run'), findsOneWidget);
    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    expect(find.text('Here is the plan'), findsNothing);
  });

  testWidgets('sheet warns about low confidence and held-back steps', (tester) async {
    await openSheet(
      tester,
      preview({
        'low_confidence': true,
        'held_back': [
          {'reason': 'not_supported', 'detail': 'click is not available on this PC yet'}
        ],
      }),
    );
    expect(find.textContaining('not very sure'), findsOneWidget);
    expect(find.text('click is not available on this PC yet'), findsOneWidget);
    expect(find.text('Run what can run'), findsOneWidget);
  });

  testWidgets('an unrunnable plan offers no Run button and explains why', (tester) async {
    await openSheet(
      tester,
      preview({'runnable': false, 'steps': [], 'note': 'I can only use Notepad here'}),
    );
    expect(find.text('Nothing to run'), findsOneWidget);
    expect(find.text('I can only use Notepad here'), findsOneWidget);
    expect(find.text('Run'), findsNothing);
    expect(find.text('Close'), findsOneWidget);
  });
}
