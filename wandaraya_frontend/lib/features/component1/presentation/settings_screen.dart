import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/environment.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../application/component1_providers.dart';
import '../data/component1_api.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});
  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _token = TextEditingController();
  bool _researchMode = false;
  bool _checking = false;
  String? _connection;

  @override
  void initState() {
    super.initState();
    ref.read(researchCredentialsProvider).readToken().then((value) {
      if (mounted && value != null) {
        _token.text = value;
      }
    });
  }

  @override
  void dispose() {
    _token.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    setState(() {
      _checking = true;
      _connection = null;
    });
    try {
      await ref.read(component1ApiProvider).health();
      if (mounted) {
        setState(() => _connection = 'Connected to the WANDARAYA API.');
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _connection = error is ApiException
              ? error.message
              : 'Connection check failed.',
        );
      }
    } finally {
      if (mounted) {
        setState(() => _checking = false);
      }
    }
  }

  Future<void> _saveToken() async {
    final value = _token.text.trim();
    if (value.isEmpty) {
      await ref.read(researchCredentialsProvider).clear();
    } else {
      await ref.read(researchCredentialsProvider).saveToken(value);
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Development research credentials updated securely.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Settings & research access')),
    bottomNavigationBar: const AppBottomNavigation(selectedIndex: 4),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _section('API connection'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Configured base URL',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                SelectableText(
                  Environment.apiBaseUrl,
                  style: const TextStyle(color: AppColors.textSecondary),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _checking ? null : _check,
                  icon: _checking
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.wifi_tethering_rounded),
                  label: const Text('Check connection'),
                ),
                if (_connection != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      _connection!,
                      style: const TextStyle(fontSize: 11),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
        _section('Research mode'),
        SwitchListTile(
          value: _researchMode,
          onChanged: (value) => setState(() => _researchMode = value),
          title: const Text(
            'Show research interfaces',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          subtitle: const Text(
            'This UI preference does not grant backend authorization.',
          ),
        ),
        if (_researchMode)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Development-only research token',
                    style: TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 7),
                  const Text(
                    'Stored using platform secure storage. Never compile tokens into the APK or source code.',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 11,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _token,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'X-Research-Token',
                    ),
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: _saveToken,
                    child: const Text('Save development credential'),
                  ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 20),
        _section('Privacy & about'),
        const ListTile(
          leading: Icon(Icons.privacy_tip_outlined),
          title: Text('Privacy'),
          subtitle: Text(
            'Travel requests are sent only to the configured WANDARAYA backend.',
          ),
        ),
        const ListTile(
          leading: Icon(Icons.info_outline_rounded),
          title: Text('About WANDARAYA'),
          subtitle: Text(
            'Multi-Agentic AI for Sustainable Tourism in Sri Lanka.',
          ),
        ),
        ListTile(
          leading: const Icon(Icons.restart_alt_rounded),
          title: const Text('Reset recommendation session'),
          onTap: () {
            ref.read(recommendationSessionProvider.notifier).clear();
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Local recommendation session cleared.'),
              ),
            );
          },
        ),
      ],
    ),
  );

  Widget _section(String label) => Padding(
    padding: const EdgeInsets.only(bottom: 9),
    child: Text(
      label.toUpperCase(),
      style: const TextStyle(
        color: AppColors.primary,
        fontSize: 11,
        fontWeight: FontWeight.w800,
        letterSpacing: .7,
      ),
    ),
  );
}
