import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wandaraya_frontend/core/theme/app_colors.dart';
import 'package:wandaraya_frontend/core/theme/app_theme.dart';
import 'package:wandaraya_frontend/features/component1/application/component1_providers.dart';
import 'package:wandaraya_frontend/features/component1/domain/component1_models.dart';
import 'package:wandaraya_frontend/features/component1/presentation/recommendations_screen.dart';
import 'package:wandaraya_frontend/features/component1/presentation/widgets/attraction_card.dart';

void main() {
  test('light theme uses the approved Component 1 palette', () {
    final theme = AppTheme.lightTheme;
    expect(theme.useMaterial3, isTrue);
    expect(theme.colorScheme.primary, AppColors.primary);
    expect(theme.scaffoldBackgroundColor, AppColors.background);
    expect(theme.colorScheme.error, AppColors.error);
  });

  testWidgets('attraction card renders a safe fallback without an image URL', (
    tester,
  ) async {
    const attraction = AttractionSummary(
      id: 1,
      name: 'Verified attraction',
      district: 'Matara',
      categories: ['Nature'],
      activities: [],
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: AttractionCard(attraction: attraction, onTap: () {}),
        ),
      ),
    );

    expect(find.text('Verified attraction'), findsOneWidget);
    expect(find.text('Matara · Nature'), findsOneWidget);
    expect(find.byIcon(Icons.landscape_rounded), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('results screen shows an honest empty session state', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          theme: AppTheme.lightTheme,
          home: const RecommendationsScreen(),
        ),
      ),
    );

    expect(find.text('No recommendation session'), findsOneWidget);
    expect(find.text('Set preferences'), findsOneWidget);
  });

  test('saved-place state toggles without inventing attraction records', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    container.read(savedPlaceIdsProvider.notifier).toggle(42);
    expect(container.read(savedPlaceIdsProvider), {42});
    container.read(savedPlaceIdsProvider.notifier).toggle(42);
    expect(container.read(savedPlaceIdsProvider), isEmpty);
  });
}
