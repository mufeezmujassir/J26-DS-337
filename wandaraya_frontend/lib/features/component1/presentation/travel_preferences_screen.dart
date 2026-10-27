import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../application/component1_providers.dart';
import '../data/component1_api.dart';
import '../domain/component1_models.dart';
import '../domain/recommendation_models.dart';

class TravelPreferencesScreen extends ConsumerStatefulWidget {
  const TravelPreferencesScreen({super.key});

  @override
  ConsumerState<TravelPreferencesScreen> createState() =>
      _TravelPreferencesScreenState();
}

class _TravelPreferencesScreenState
    extends ConsumerState<TravelPreferencesScreen> {
  final _formKey = GlobalKey<FormState>();
  final _query = TextEditingController();
  final _additional = TextEditingController();
  DateTime _date = DateTime.now().add(const Duration(days: 1));
  TimeOfDay _time = const TimeOfDay(hour: 9, minute: 0);
  TaxonomyItem? _district;
  final Set<String> _interests = {};
  int _groupSize = 1;
  int? _durationMinutes = 120;
  bool _submitting = false;

  @override
  void dispose() {
    _query.dispose();
    _additional.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final token = await ref.read(researchCredentialsProvider).readToken();
    if (!mounted) return;
    if (token == null || token.length < 32) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Configure research authorization before using experimental recommendations.',
          ),
        ),
      );
      context.push('/settings');
      return;
    }

    final request = TravelRecommendationRequest(
      query: _query.text.trim(),
      destinationDistrictId: _district?.id,
      travelDateTime: DateTime(
        _date.year,
        _date.month,
        _date.day,
        _time.hour,
        _time.minute,
      ),
      requestedActivities: const [],
      interests: _interests.toList(),
      groupSize: _groupSize,
      durationMinutes: _durationMinutes,
      additionalPreferences: _additional.text.trim().isEmpty
          ? null
          : _additional.text.trim(),
      configuration: RerankerConfiguration.r3,
    );

    setState(() => _submitting = true);
    try {
      final response = await ref
          .read(component1ApiProvider)
          .recommend(request, token: token);
      ref.read(recommendationSessionProvider.notifier).save(request, response);
      if (mounted) context.go('/recommendations');
    } catch (error) {
      if (!mounted) return;
      final message = error is ApiException
          ? error.message
          : 'The recommendation request failed.';
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final districts = ref.watch(districtsProvider);
    final categories = ref.watch(categoriesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Smart travel preferences')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            Container(
              padding: const EdgeInsets.all(15),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(18),
              ),
              child: const Row(
                children: [
                  Icon(Icons.science_outlined, color: AppColors.primary),
                  SizedBox(width: 11),
                  Expanded(
                    child: Text(
                      'Recommendations are experimental research outputs and are not production-validated.',
                      style: TextStyle(fontSize: 11, height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            _label('Describe your trip'),
            TextFormField(
              controller: _query,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                hintText:
                    'I want a peaceful beach near Mirissa tomorrow morning.',
              ),
              validator: (value) => (value ?? '').trim().length < 2
                  ? 'Describe the kind of place you want.'
                  : null,
            ),
            const SizedBox(height: 18),
            _label('Destination district'),
            districts.when(
              loading: () => const LinearProgressIndicator(),
              error: (_, _) => const Text(
                'Districts are currently unavailable.',
                style: TextStyle(color: AppColors.error),
              ),
              data: (values) => DropdownButtonFormField<TaxonomyItem>(
                initialValue: _district,
                hint: const Text('Optional — choose a district'),
                items: values
                    .map(
                      (item) =>
                          DropdownMenuItem(value: item, child: Text(item.name)),
                    )
                    .toList(),
                onChanged: (value) => setState(() => _district = value),
              ),
            ),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: _PickerTile(
                    label: 'Travel date',
                    value: DateFormat('dd MMM yyyy').format(_date),
                    icon: Icons.calendar_today_outlined,
                    onTap: _pickDate,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _PickerTile(
                    label: 'Arrival time',
                    value: _time.format(context),
                    icon: Icons.schedule_rounded,
                    onTap: _pickTime,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            _label('Travel interests'),
            categories.when(
              loading: () => const LinearProgressIndicator(),
              error: (_, _) =>
                  const Text('Interest taxonomy is currently unavailable.'),
              data: (values) => Wrap(
                spacing: 8,
                runSpacing: 7,
                children: values
                    .map(
                      (item) => FilterChip(
                        label: Text(item.name),
                        selected: _interests.contains(item.name),
                        onSelected: (selected) => setState(
                          () => selected
                              ? _interests.add(item.name)
                              : _interests.remove(item.name),
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 20),
            _label('Group size'),
            Row(
              children: [
                IconButton.outlined(
                  onPressed: _groupSize > 1
                      ? () => setState(() => _groupSize--)
                      : null,
                  icon: const Icon(Icons.remove),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 18),
                  child: Text(
                    '$_groupSize',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton.outlined(
                  onPressed: _groupSize < 100
                      ? () => setState(() => _groupSize++)
                      : null,
                  icon: const Icon(Icons.add),
                ),
              ],
            ),
            const SizedBox(height: 18),
            _label('Visit duration'),
            DropdownButtonFormField<int?>(
              initialValue: _durationMinutes,
              items: const [
                DropdownMenuItem(value: null, child: Text('Not specified')),
                DropdownMenuItem(value: 60, child: Text('About 1 hour')),
                DropdownMenuItem(value: 120, child: Text('About 2 hours')),
                DropdownMenuItem(value: 240, child: Text('Half day')),
                DropdownMenuItem(value: 480, child: Text('Full day')),
              ],
              onChanged: (value) => setState(() => _durationMinutes = value),
            ),
            const SizedBox(height: 18),
            _label('Additional preferences'),
            TextField(
              controller: _additional,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                hintText: 'Optional accessibility, pace or travel preferences',
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _submitting ? null : _submit,
              icon: _submitting
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.auto_awesome_rounded),
              label: Text(
                _submitting ? 'Evaluating context…' : 'Find my perfect places',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _label(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Text(text, style: const TextStyle(fontWeight: FontWeight.w800)),
  );

  Future<void> _pickDate() async {
    final value = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (value != null) setState(() => _date = value);
  }

  Future<void> _pickTime() async {
    final value = await showTimePicker(context: context, initialTime: _time);
    if (value != null) setState(() => _time = value);
  }
}

class _PickerTile extends StatelessWidget {
  const _PickerTile({
    required this.label,
    required this.value,
    required this.icon,
    required this.onTap,
  });
  final String label;
  final String value;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(16),
    child: Ink(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: AppColors.primary),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    ),
  );
}
