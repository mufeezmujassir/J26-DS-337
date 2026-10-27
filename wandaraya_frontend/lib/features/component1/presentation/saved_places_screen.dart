import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/async_states.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../application/component1_providers.dart';
import 'widgets/attraction_card.dart';

class SavedPlacesScreen extends ConsumerWidget {
  const SavedPlacesScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ids = ref.watch(savedPlaceIdsProvider);
    final attractions = ref.watch(attractionListProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Saved places')),
      bottomNavigationBar: const AppBottomNavigation(selectedIndex: 3),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: ids.isEmpty
            ? const EmptyState(
                title: 'No saved places',
                message: 'Bookmark a verified attraction to keep it here.',
              )
            : attractions.when(
                loading: () => const LoadingCards(),
                error: (_, _) => AppErrorState(
                  message:
                      'Saved attraction details are currently unavailable.',
                  onRetry: () => ref.invalidate(attractionListProvider),
                ),
                data: (values) {
                  final saved = values
                      .where((item) => ids.contains(item.id))
                      .toList();
                  if (saved.isEmpty) {
                    return const EmptyState(
                      title: 'Saved places are outside this page',
                      message: 'Open Discover and pull to refresh the current attraction listing.',
                    );
                  }
                  return ListView(
                    children: saved
                        .map(
                          (item) => AttractionCard(
                            attraction: item,
                            onTap: () =>
                                context.push('/attractions/${item.id}'),
                          ),
                        )
                        .toList(),
                  );
                },
              ),
      ),
    );
  }
}
