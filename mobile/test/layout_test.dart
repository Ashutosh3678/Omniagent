import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/models.dart';
import 'package:omniagent/screens/plan_sheet.dart';
import 'package:omniagent/screens/welcome_screen.dart';
import 'package:omniagent/theme.dart';
import 'package:omniagent/widgets.dart';

/// Small phone + large system font: the harshest case for overflow.
Future<void> pumpSmall(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(320 * 2, 568 * 2);
  tester.view.devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: buildAppTheme(),
    builder: (context, app) => MediaQuery(
      data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(1.6)),
      child: app!,
    ),
    home: child,
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('welcome screen does not overflow', (tester) async {
    await pumpSmall(tester, const WelcomeScreen());
    expect(tester.takeException(), isNull);
  });

  testWidgets('task tiles and pills do not overflow with long text', (tester) async {
    const long = 'Open the browser, search for a very long query, and then write everything into a document';
    await pumpSmall(
      tester,
      const Scaffold(
        body: Column(
          children: [
            TaskTile(task: TaskItem(title: long, when: '2026-10-30T10:00:00Z', status: TaskStatus.partial)),
            Pill(label: 'Access expired for this really long device', color: AppColors.warning),
          ],
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('plan sheet with many steps scrolls instead of overflowing', (tester) async {
    final preview = PlanPreview.fromJson({
      'planner': 'groq',
      'steps': [for (var i = 0; i < 20; i++) {'description': 'Step number $i does something long'}],
      'held_back': [
        {'reason': 'x', 'detail': 'click is not available on this PC yet'}
      ],
      'runnable': true,
      'low_confidence': true,
    });
    await pumpSmall(tester, Scaffold(body: PlanSheet(preview: preview)));
    expect(tester.takeException(), isNull);
    expect(find.text('Run what can run'), findsOneWidget);
  });
}
