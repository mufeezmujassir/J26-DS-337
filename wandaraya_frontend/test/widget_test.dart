import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wandaraya_frontend/app.dart';
import 'package:wandaraya_frontend/features/component1/application/component1_providers.dart';

void main() {
  testWidgets('launches into the live Discover experience', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          attractionListProvider.overrideWith((ref) async => []),
          categoriesProvider.overrideWith((ref) async => []),
        ],
        child: const WandarayaApp(),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('WANDARAYA'), findsOneWidget);
    expect(
      find.text('Where will your next\nadventure take you?'),
      findsOneWidget,
    );
  });
}
