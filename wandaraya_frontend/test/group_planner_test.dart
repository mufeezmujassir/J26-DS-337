import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wandaraya_frontend/features/planner/application/group_planner_provider.dart';

void main() {
  test('creating a travel group updates planner state', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final initialCount = container.read(groupPlannerProvider).length;
    final created = container
        .read(groupPlannerProvider.notifier)
        .addGroup(name: 'Kandy Weekend', location: 'Colombo');

    expect(container.read(groupPlannerProvider), hasLength(initialCount + 1));
    expect(created.name, 'Kandy Weekend');
    expect(created.location, 'Colombo');
    expect(created.members.single.name, 'You');
  });
}
