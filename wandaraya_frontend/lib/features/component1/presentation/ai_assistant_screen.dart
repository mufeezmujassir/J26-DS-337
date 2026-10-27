import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../data/component1_api.dart';
import '../domain/recommendation_models.dart';

class AiAssistantScreen extends ConsumerStatefulWidget {
  const AiAssistantScreen({super.key});

  @override
  ConsumerState<AiAssistantScreen> createState() => _AiAssistantScreenState();
}

class _AiAssistantScreenState extends ConsumerState<AiAssistantScreen> {
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  final List<_Message> _messages = [];
  late String _sessionId;
  bool _sending = false;
  String? _lastFailedMessage;
  List<String> _nodes = const [];

  @override
  void initState() {
    super.initState();
    _newSession();
  }

  void _newSession() {
    _sessionId = 'flutter-${DateTime.now().millisecondsSinceEpoch}';
    _messages
      ..clear()
      ..add(
        const _Message(
          false,
          'Describe your Sri Lankan trip and I will use the research workflow to clarify missing details.',
        ),
      );
    _nodes = const [];
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send([String? retry]) async {
    final text = (retry ?? _controller.text).trim();
    if (text.length < 2 || _sending) return;
    _controller.clear();
    setState(() {
      _sending = true;
      _lastFailedMessage = null;
      if (retry == null) _messages.add(_Message(true, text));
    });
    _toBottom();

    try {
      final token = await ref.read(researchCredentialsProvider).readToken();
      final response = await ref
          .read(component1ApiProvider)
          .agent(sessionId: _sessionId, message: text, token: token);
      if (!mounted) return;
      _apply(response);
    } catch (error) {
      if (!mounted) return;
      final message = error is ApiException
          ? error.message
          : 'The LangGraph request failed.';
      setState(() {
        _lastFailedMessage = text;
        final errorMessage = _Message(false, message, isError: true);
        if (_messages.isNotEmpty && _messages.last.isError) {
          _messages[_messages.length - 1] = errorMessage;
        } else {
          _messages.add(errorMessage);
        }
      });
    } finally {
      if (mounted) setState(() => _sending = false);
      _toBottom();
    }
  }

  void _apply(AgentResponse response) {
    setState(() {
      _nodes = response.nodesExecuted;
      final text = response.clarificationRequired
          ? response.clarificationQuestion ??
                'Please provide the missing trip detail.'
          : response.humanResponse ??
                (response.recommendations.isEmpty
                    ? 'The workflow completed without recommendation results.'
                    : 'I found ${response.recommendations.length} research recommendations.');
      _messages.add(_Message(false, text));
      if (response.itinerary.isNotEmpty) {
        _messages.add(
          _Message(
            false,
            [
              response.notRecommended.isNotEmpty
                  ? 'Weather-adjusted indoor/sheltered alternatives · ${response.itinerary.first.visitDate}'
                  : 'Suggested itinerary · ${response.itinerary.first.visitDate}',
              ...response.itinerary.map((stop) {
                return [
                  '${stop.order}. ${stop.startTime}–${stop.endTime} · ${stop.attractionName}',
                  if (stop.location?.isNotEmpty ?? false)
                    'Location: ${stop.location}',
                  if (stop.transferMinutes > 0)
                    'Estimated transfer: ${stop.transferMinutes} minutes',
                  if (stop.description?.isNotEmpty ?? false) stop.description!,
                  if (stop.expectedBehavior?.isNotEmpty ?? false)
                    'Expected conditions and behavior:\n${stop.expectedBehavior!}',
                  'Why it fits: ${stop.reason}',
                ].join('\n');
              }),
            ].join('\n\n'),
          ),
        );
        final scheduledIds = response.itinerary
            .map((stop) => stop.attractionId)
            .toSet();
        final rejectedIds = response.notRecommended
            .map((item) => item.attractionId)
            .toSet();
        final alternatives = response.recommendations
            .where(
              (item) =>
                  !scheduledIds.contains(item.attractionId) &&
                  !rejectedIds.contains(item.attractionId),
            )
            .take(3)
            .toList();
        if (alternatives.isNotEmpty) {
          _messages.add(
            _Message(
              false,
              'Other relevant options:\n${alternatives.map((item) => '• ${item.name}${item.city == null ? '' : ' · ${item.city}'}').join('\n')}',
            ),
          );
        }
      } else if (response.recommendations.isNotEmpty) {
        _messages.add(
          _Message(
            false,
            response.recommendations
                .take(5)
                .map(
                  (item) =>
                      '• ${item.name}${item.city == null ? '' : ' · ${item.city}'}\n${item.description ?? item.explanation}',
                )
                .join('\n\n'),
          ),
        );
      }
      if (response.notRecommended.isNotEmpty) {
        _messages.add(
          _Message(
            false,
            [
              'Not recommended for outdoor visits at the requested time:',
              ...response.notRecommended.map(
                (item) =>
                    '• ${item.attractionName}${item.location == null ? '' : ' · ${item.location}'}\n${item.reason}',
              ),
            ].join('\n\n'),
            isError: true,
          ),
        );
      }
    });
  }

  void _toBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (_scroll.hasClients) {
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    }
  });

  @override
  Widget build(BuildContext context) => Scaffold(
    bottomNavigationBar: const AppBottomNavigation(selectedIndex: 1),
    appBar: AppBar(
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('AI travel assistant'),
          Text(
            'Experimental LangGraph workflow',
            style: TextStyle(fontSize: 10, fontWeight: FontWeight.normal),
          ),
        ],
      ),
      actions: [
        IconButton(
          tooltip: 'New research session',
          onPressed: _newSession,
          icon: const Icon(Icons.add_comment_outlined),
        ),
      ],
    ),
    body: Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
          color: AppColors.surfaceMuted,
          child: Text(
            'Session: $_sessionId · Development in-memory checkpoint',
            style: const TextStyle(
              fontSize: 10,
              color: AppColors.textSecondary,
            ),
          ),
        ),
        if (_nodes.isNotEmpty)
          ExpansionTile(
            dense: true,
            title: Text(
              '${_nodes.length} verified workflow nodes executed',
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
            ),
            children: _nodes
                .map(
                  (node) => ListTile(
                    dense: true,
                    leading: const Icon(
                      Icons.check_circle_outline,
                      color: AppColors.primary,
                      size: 18,
                    ),
                    title: Text(node),
                  ),
                )
                .toList(),
          ),
        Expanded(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.all(18),
            itemCount: _messages.length + (_sending ? 1 : 0),
            itemBuilder: (context, index) {
              if (index == _messages.length) return const _Typing();
              final message = _messages[index];
              return _Bubble(message: message);
            },
          ),
        ),
        if (_messages.length == 1)
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                _Prompt(
                  label: 'Nature near Ella',
                  onTap: () => _send('Suggest nature places near Ella.'),
                ),
                _Prompt(
                  label: 'Peaceful Mirissa beach',
                  onTap: () => _send('I want a peaceful beach near Mirissa.'),
                ),
              ],
            ),
          ),
        if (_lastFailedMessage != null)
          TextButton.icon(
            onPressed: () => _send(_lastFailedMessage),
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Retry last request'),
          ),
        Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
          decoration: const BoxDecoration(
            color: AppColors.surface,
            border: Border(top: BorderSide(color: AppColors.divider)),
          ),
          child: SafeArea(
            top: false,
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      hintText: 'Ask about your Sri Lankan trip…',
                    ),
                  ),
                ),
                const SizedBox(width: 9),
                IconButton.filled(
                  onPressed: _sending ? null : _send,
                  icon: const Icon(Icons.send_rounded),
                ),
              ],
            ),
          ),
        ),
      ],
    ),
  );
}

class _Message {
  const _Message(this.user, this.text, {this.isError = false});
  final bool user;
  final String text;
  final bool isError;
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});
  final _Message message;
  @override
  Widget build(BuildContext context) => Align(
    alignment: message.user ? Alignment.centerRight : Alignment.centerLeft,
    child: Container(
      constraints: const BoxConstraints(maxWidth: 680),
      margin: const EdgeInsets.only(bottom: 11),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: message.user
            ? AppColors.primaryDark
            : (message.isError ? const Color(0xFFFFECEC) : AppColors.surface),
        borderRadius: BorderRadius.circular(17),
        border: message.user
            ? null
            : Border.all(
                color: message.isError ? AppColors.error : AppColors.divider,
              ),
      ),
      child: Text(
        message.text,
        style: TextStyle(
          color: message.user ? Colors.white : AppColors.textPrimary,
          height: 1.45,
        ),
      ),
    ),
  );
}

class _Typing extends StatelessWidget {
  const _Typing();
  @override
  Widget build(BuildContext context) => const Align(
    alignment: Alignment.centerLeft,
    child: Padding(
      padding: EdgeInsets.all(14),
      child: SizedBox.square(
        dimension: 22,
        child: CircularProgressIndicator(strokeWidth: 2),
      ),
    ),
  );
}

class _Prompt extends StatelessWidget {
  const _Prompt({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(right: 8),
    child: ActionChip(label: Text(label), onPressed: onTap),
  );
}
