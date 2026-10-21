import 'package:flutter_test/flutter_test.dart';
import 'package:wandaraya_frontend/app.dart';

void main() {
  testWidgets('shows the Wandaraya splash experience', (tester) async {
    await tester.pumpWidget(const WandarayaApp());
    await tester.pump();

    expect(find.text('WANDARAYA'), findsOneWidget);
    expect(find.text('Explore Sri Lanka, intelligently.'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Sri Lanka,\nmade personal.'), findsOneWidget);
  });
}
