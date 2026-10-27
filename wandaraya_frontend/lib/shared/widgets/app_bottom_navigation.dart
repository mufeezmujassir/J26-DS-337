import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';

class AppBottomNavigation extends StatelessWidget {
  const AppBottomNavigation({super.key, required this.selectedIndex});
  final int selectedIndex;

  @override
  Widget build(BuildContext context) => NavigationBar(
    selectedIndex: selectedIndex,
    backgroundColor: AppColors.surface,
    indicatorColor: AppColors.surfaceMuted,
    height: 72,
    labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
    onDestinationSelected: (index) {
      switch (index) {
        case 0:
          context.go('/discover');
          break;
        case 1:
          context.go('/assistant');
          break;
        case 2:
          context.go('/recommendations');
          break;
        case 3:
          context.go('/saved');
          break;
        case 4:
          context.go('/settings');
          break;
      }
    },
    destinations: const [
      NavigationDestination(
        icon: Icon(Icons.explore_outlined),
        selectedIcon: Icon(Icons.explore_rounded),
        label: 'Discover',
      ),
      NavigationDestination(
        icon: Icon(Icons.auto_awesome_outlined),
        selectedIcon: Icon(Icons.auto_awesome_rounded),
        label: 'Assistant',
      ),
      NavigationDestination(
        icon: Icon(Icons.recommend_outlined),
        selectedIcon: Icon(Icons.recommend_rounded),
        label: 'Results',
      ),
      NavigationDestination(
        icon: Icon(Icons.bookmark_border_rounded),
        selectedIcon: Icon(Icons.bookmark_rounded),
        label: 'Saved',
      ),
      NavigationDestination(
        icon: Icon(Icons.settings_outlined),
        selectedIcon: Icon(Icons.settings_rounded),
        label: 'Settings',
      ),
    ],
  );
}
