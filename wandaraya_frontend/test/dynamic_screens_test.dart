import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wandaraya_frontend/core/theme/app_theme.dart';
import 'package:wandaraya_frontend/features/home/home_screen.dart';
import 'package:wandaraya_frontend/features/planner/presentation/group_chat_screen.dart';
import 'package:wandaraya_frontend/features/planner/presentation/group_planner_screen.dart';
import 'package:wandaraya_frontend/features/planner/presentation/itinerary_screen.dart';

void main() {
  testWidgets('dynamic planner screens render at phone size', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    Future<void> show(Widget screen) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(theme: AppTheme.lightTheme, home: screen),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    }

    await show(const HomeScreen());
    expect(find.text('Sri Lanka awaits'), findsOneWidget);

    await show(const GroupPlannerScreen());
    expect(find.text('Group planner'), findsOneWidget);

    await show(const GroupChatScreen(groupId: 'ella-squad'));
    expect(find.textContaining('Ella Squad'), findsWidgets);

    await show(const ItineraryScreen());
    expect(find.text('AI itinerary ready'), findsOneWidget);
  });
}
