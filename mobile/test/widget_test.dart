import 'package:flutter_test/flutter_test.dart';
import 'package:omniagent/main.dart';

void main() {
  testWidgets('Welcome screen shows login', (tester) async {
    await tester.pumpWidget(const OmniAgentApp());

    expect(find.text('OmniAgent'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('Sign up'), findsOneWidget);
  });
}
