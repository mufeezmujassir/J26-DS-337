import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'WANDARAYA',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.notifications_outlined),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Ayubowan! 👋',
            style: Theme.of(context).textTheme.headlineMedium
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text('Where would you like to explore today?'),
          const SizedBox(height: 28),

          Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.auto_awesome,
                    color: AppColors.primary,
                    size: 36,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Your AI Travel Companion',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Discover destinations and plan '
                    'personalized sustainable trips '
                    'across Sri Lanka.',
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 28),
          Text(
            'Explore Features',
            style: Theme.of(context).textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),

          const _FeatureTile(
            icon: Icons.travel_explore,
            title: 'Smart Recommendations',
            description: 'Discover places matching your preferences',
          ),
          const _FeatureTile(
            icon: Icons.route,
            title: 'AI Trip Planner',
            description: 'Create personalized travel itineraries',
          ),
          const _FeatureTile(
            icon: Icons.groups_outlined,
            title: 'Group Travel',
            description: 'Plan trips together with friends',
          ),
          const _FeatureTile(
            icon: Icons.map_outlined,
            title: 'Smart Transportation',
            description: 'Explore travel routes and options',
          ),
        ],
      ),
    );
  }
}

class _FeatureTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _FeatureTile({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: Icon(icon, color: AppColors.primary, size: 30),
        title: Text(title),
        subtitle: Text(description),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }
}
