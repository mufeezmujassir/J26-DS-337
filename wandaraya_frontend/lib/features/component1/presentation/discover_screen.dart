import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/async_states.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../application/component1_providers.dart';
import '../data/component1_api.dart';
import '../domain/component1_models.dart';
import 'widgets/attraction_card.dart';

class DiscoverScreen extends ConsumerStatefulWidget {
  const DiscoverScreen({super.key});

  @override
  ConsumerState<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends ConsumerState<DiscoverScreen> {
  final _searchController = TextEditingController();
  Timer? _debounce;
  Future<List<AttractionSummary>>? _searchFuture;
  String? _selectedCategory;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _scheduleSearch(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 450), () {
      if (!mounted) return;
      setState(() {
        _searchFuture = value.trim().length < 2
            ? null
            : ref.read(component1ApiProvider).semanticSearch(value.trim());
      });
    });
  }

  Future<void> _refresh() async {
    ref.invalidate(attractionListProvider);
    ref.invalidate(categoriesProvider);
    await ref.read(attractionListProvider.future);
  }

  @override
  Widget build(BuildContext context) {
    final categories = ref.watch(categoriesProvider);
    final attractions = ref.watch(attractionListProvider);

    return Scaffold(
      bottomNavigationBar: const AppBottomNavigation(selectedIndex: 0),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: _DiscoverHeader(
                controller: _searchController,
                onChanged: _scheduleSearch,
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 22, 20, 30),
              sliver: SliverList.list(
                children: [
                  Row(
                    children: [
                      Text(
                        'Explore by interest',
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => context.push('/preferences'),
                        child: const Text('Smart search'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  categories.when(
                    loading: () => const LinearProgressIndicator(),
                    error: (_, _) => const Text(
                      'Activity categories are unavailable.',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                    data: (items) => SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: items.take(10).map((item) {
                          final selected = _selectedCategory == item.name;
                          return Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: FilterChip(
                              selected: selected,
                              label: Text(item.name),
                              onSelected: (value) => setState(
                                () => _selectedCategory = value
                                    ? item.name
                                    : null,
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    _searchFuture == null
                        ? 'Places from the knowledge base'
                        : 'Semantic search results',
                    style: Theme.of(context).textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 5),
                  const Text(
                    'Live data from the WANDARAYA attraction knowledge base.',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (_searchFuture != null)
                    FutureBuilder<List<AttractionSummary>>(
                      future: _searchFuture,
                      builder: (context, snapshot) {
                        if (snapshot.connectionState ==
                            ConnectionState.waiting) {
                          return const LoadingCards();
                        }
                        if (snapshot.hasError) {
                          return _error(
                            snapshot.error ??
                                const ApiException('Semantic search failed.'),
                            () => _scheduleSearch(_searchController.text),
                          );
                        }
                        return _results(snapshot.data ?? const []);
                      },
                    )
                  else
                    attractions.when(
                      loading: () => const LoadingCards(),
                      error: (error, _) => _error(
                        error,
                        () => ref.invalidate(attractionListProvider),
                      ),
                      data: _results,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/preferences'),
        icon: const Icon(Icons.auto_awesome_rounded),
        label: const Text('Find my places'),
      ),
    );
  }

  Widget _results(List<AttractionSummary> values) {
    final filtered = _selectedCategory == null
        ? values
        : values
              .where((item) => item.categories.contains(_selectedCategory))
              .toList();
    if (filtered.isEmpty) {
      return const EmptyState(
        title: 'No places found',
        message: 'Try another description or clear the selected interest.',
      );
    }
    return Column(
      children: filtered
          .map(
            (item) => AttractionCard(
              attraction: item,
              onTap: () => context.push('/attractions/${item.id}'),
            ),
          )
          .toList(),
    );
  }

  Widget _error(Object error, VoidCallback retry) => AppErrorState(
    message: error is ApiException
        ? error.message
        : 'Unable to connect to the WANDARAYA recommendation service.',
    onRetry: retry,
  );
}

class _DiscoverHeader extends StatelessWidget {
  const _DiscoverHeader({required this.controller, required this.onChanged});
  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => Container(
    padding: EdgeInsets.fromLTRB(
      20,
      MediaQuery.paddingOf(context).top + 18,
      20,
      26,
    ),
    decoration: const BoxDecoration(
      color: AppColors.primaryDark,
      borderRadius: BorderRadius.vertical(bottom: Radius.circular(32)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Expanded(
              child: Text(
                'WANDARAYA',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 2,
                ),
              ),
            ),
            CircleAvatar(
              backgroundColor: Colors.white12,
              foregroundColor: Colors.white,
              child: Icon(Icons.person_outline_rounded),
            ),
          ],
        ),
        const SizedBox(height: 26),
        const Text(
          'Where will your next\nadventure take you?',
          style: TextStyle(
            color: Colors.white,
            fontSize: 28,
            height: 1.12,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 10),
        const Text(
          'Discover places matched to your interests, travel time and available local context.',
          style: TextStyle(color: Colors.white70, height: 1.45),
        ),
        const SizedBox(height: 19),
        TextField(
          controller: controller,
          onChanged: onChanged,
          decoration: const InputDecoration(
            hintText: 'Describe your perfect Sri Lankan adventure…',
            prefixIcon: Icon(Icons.search_rounded),
            fillColor: Colors.white,
          ),
        ),
      ],
    ),
  );
}
