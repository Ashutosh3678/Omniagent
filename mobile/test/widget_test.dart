import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/main.dart';

void main() {
  testWidgets('Welcome screen shows login', (tester) async {
    await tester.pumpWidget(const OmniAgentApp());

    expect(find.text('OmniAgent'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('Sign up'), findsOneWidget);
  });

  testWidgets('Login validates input before calling the server', (tester) async {
    await tester.pumpWidget(const OmniAgentApp());

    await tester.tap(find.text('Log in'));
    await tester.pump();
    expect(find.text('Enter a valid email address.'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'alex@example.com');
    await tester.tap(find.text('Sign up'));
    await tester.pump();
    expect(find.text('Choose a password with at least 8 characters.'), findsOneWidget);
  });
}
