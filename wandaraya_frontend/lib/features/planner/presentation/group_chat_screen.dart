import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../application/group_planner_provider.dart';
import '../domain/travel_group.dart';

class GroupChatScreen extends ConsumerStatefulWidget {
  const GroupChatScreen({super.key, required this.groupId});

  final String groupId;

  @override
  ConsumerState<GroupChatScreen> createState() => _GroupChatScreenState();
}

class _GroupChatScreenState extends ConsumerState<GroupChatScreen> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  int _selectedTab = 0;
  bool _showMood = true;
  bool _planning = false;
  bool _generated = false;
  int _questionIndex = -1;

  final List<ChatMessage> _groupMessages = [
    const ChatMessage(
      sender: 'Kasun',
      message: "Guys, we're 4 people going to Ella tomorrow. Any ideas?",
      time: '10:23 AM',
    ),
    const ChatMessage(
      sender: 'Nimal',
      message: 'api tired nisaa easy hike ekak yamu',
      translation: "We're tired, so let's do an easy hike.",
      tag: 'Singlish',
      time: '10:24 AM',
    ),
  ];

  final List<ChatMessage> _aiMessages = [
    const ChatMessage(
      sender: 'Place Agent',
      tag: 'Destination expert',
      message: 'I’m ready to build a group-friendly Ella itinerary. Type /plan to begin.',
      time: 'Now',
    ),
  ];

  static const _questions = [
    "What’s your approximate budget per person (LKR)?",
    'Which experiences matter most: nature, photography, food, or adventure?',
    'How active should the trip feel: relaxed, balanced, or energetic?',
    'Any food, mobility, or accommodation preferences I should respect?',
  ];

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  TravelGroup _group(List<TravelGroup> groups) => groups.firstWhere(
    (group) => group.id == widget.groupId,
    orElse: () => groups.first,
  );

  Future<void> _send() async {
    final value = _messageController.text.trim();
    if (value.isEmpty) return;
    _messageController.clear();

    final message = ChatMessage(
      sender: 'You',
      message: value,
      time: 'Just now',
      isCurrentUser: true,
    );
    setState(() {
      if (_selectedTab == 0) {
        _groupMessages.add(message);
      } else {
        _aiMessages.add(message);
      }
    });
    _scrollToBottom();

    if (_selectedTab == 1) await _advancePlanner(value);
  }

  Future<void> _advancePlanner(String value) async {
    if (_generated || _planning) return;

    if (_questionIndex == -1 && value.toLowerCase() != '/plan') {
      await _agentReply(
        'Type /plan whenever you want me to build the itinerary.',
      );
      return;
    }

    if (_questionIndex < _questions.length - 1) {
      _questionIndex++;
      await _agentReply(_questions[_questionIndex]);
      return;
    }

    setState(() => _planning = true);
    _scrollToBottom();
    await Future<void>.delayed(const Duration(milliseconds: 1400));
    if (!mounted) return;
    setState(() {
      _planning = false;
      _generated = true;
    });
    _scrollToBottom();
  }

  Future<void> _agentReply(String message) async {
    await Future<void>.delayed(const Duration(milliseconds: 450));
    if (!mounted) return;
    setState(() {
      _aiMessages.add(
        ChatMessage(
          sender: 'Place Agent',
          tag: 'Destination expert',
          message: message,
          time: 'Just now',
        ),
      );
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final groups = ref.watch(groupPlannerProvider);
    final group = _group(groups);
    final messages = _selectedTab == 0 ? _groupMessages : _aiMessages;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      bottomNavigationBar: const AppBottomNavigation(selectedIndex: 1),
      body: Column(
        children: [
          _ChatHeader(
            group: group,
            selectedTab: _selectedTab,
            showMood: _showMood,
            onBack: () => context.pop(),
            onMood: () => setState(() => _showMood = !_showMood),
            onTabChanged: (value) => setState(() => _selectedTab = value),
          ),
          Expanded(
            child: ListView(
              controller: _scrollController,
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
              children: [
                if (_selectedTab == 0 && _showMood) ...[
                  _MoodAnalysis(group: group),
                  const SizedBox(height: 18),
                ],
                ...messages.map(
                  (message) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _MessageBubble(message: message),
                  ),
                ),
                if (_selectedTab == 1 && _planning) const _PlanningProgress(),
                if (_selectedTab == 1 && _generated)
                  _GeneratedItineraryCard(
                    onOpen: () => context.push('/itinerary'),
                  ),
              ],
            ),
          ),
          if (_selectedTab == 1 && _questionIndex >= 0 && !_generated)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Question ${(_questionIndex + 1).clamp(1, 4)} of 4',
                  style: const TextStyle(
                    color: AppColors.primary,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
          _MessageComposer(
            controller: _messageController,
            hint: _selectedTab == 1 && _questionIndex >= 0
                ? 'Your answer…'
                : 'Type in English, Sinhala or Singlish…',
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({
    required this.group,
    required this.selectedTab,
    required this.showMood,
    required this.onBack,
    required this.onMood,
    required this.onTabChanged,
  });

  final TravelGroup group;
  final int selectedTab;
  final bool showMood;
  final VoidCallback onBack;
  final VoidCallback onMood;
  final ValueChanged<int> onTabChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
        16,
        MediaQuery.paddingOf(context).top + 12,
        16,
        14,
      ),
      color: AppColors.primaryDark,
      child: Column(
        children: [
          Row(
            children: [
              IconButton(
                onPressed: onBack,
                color: Colors.white,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              const SizedBox(width: 4),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${group.name} ${group.emoji}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${group.members.length} members · ${group.location}',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton.icon(
                onPressed: onMood,
                style: TextButton.styleFrom(
                  backgroundColor: Colors.white.withValues(alpha: .13),
                  foregroundColor: Colors.white,
                ),
                icon: Icon(
                  showMood
                      ? Icons.psychology_rounded
                      : Icons.psychology_outlined,
                  size: 17,
                ),
                label: const Text('Mood'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .12),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Expanded(
                  child: _TabButton(
                    icon: Icons.groups_outlined,
                    label: 'Group chat',
                    selected: selectedTab == 0,
                    onTap: () => onTabChanged(0),
                  ),
                ),
                Expanded(
                  child: _TabButton(
                    icon: Icons.smart_toy_outlined,
                    label: 'AI agent',
                    selected: selectedTab == 1,
                    onTap: () => onTabChanged(1),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 9),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text(
              '＠ Type /plan to generate itinerary · @name to mention a member',
              style: TextStyle(color: Colors.white70, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: selected ? Colors.white : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 16,
              color: selected ? AppColors.primaryDark : Colors.white70,
            ),
            const SizedBox(width: 7),
            Text(
              label,
              style: TextStyle(
                color: selected ? AppColors.primaryDark : Colors.white70,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MoodAnalysis extends StatelessWidget {
  const _MoodAnalysis({required this.group});

  final TravelGroup group;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(19),
        border: Border.all(color: AppColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.air_rounded, color: AppColors.primary, size: 20),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Group emotion analysis',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
              _StatusPill(label: 'Tired', color: Color(0xFFFFE7A6)),
            ],
          ),
          const SizedBox(height: 14),
          ...group.members.map(
            (member) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 15,
                    backgroundColor: AppColors.surfaceMuted,
                    child: Text(
                      member.initial,
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 11,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 68,
                    child: Text(
                      member.name,
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(99),
                      child: LinearProgressIndicator(
                        value: member.moodScore,
                        minHeight: 7,
                        color: member.moodColor,
                        backgroundColor: AppColors.surfaceMuted,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 44,
                    child: Text(
                      member.mood,
                      textAlign: TextAlign.right,
                      style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 10,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const Divider(),
          const SizedBox(height: 6),
          const Text(
            'Group preferences',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 11),
          ),
          const SizedBox(height: 10),
          const _Preference(label: 'Nature', score: .90),
          const _Preference(label: 'Photography', score: .85),
          const _Preference(label: 'Local food', score: .72),
        ],
      ),
    );
  }
}

class _Preference extends StatelessWidget {
  const _Preference({required this.label, required this.score});

  final String label;
  final double score;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(label, style: const TextStyle(fontSize: 11)),
          ),
          Expanded(
            child: LinearProgressIndicator(
              value: score,
              minHeight: 5,
              borderRadius: BorderRadius.circular(99),
              color: AppColors.primaryDark,
              backgroundColor: AppColors.surfaceMuted,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '${(score * 100).round()}%',
            style: const TextStyle(
              fontSize: 10,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    if (message.isCurrentUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: const BoxConstraints(maxWidth: 275),
          padding: const EdgeInsets.all(14),
          decoration: const BoxDecoration(
            color: AppColors.primaryDark,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(17),
              topRight: Radius.circular(5),
              bottomLeft: Radius.circular(17),
              bottomRight: Radius.circular(17),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                message.message,
                style: const TextStyle(color: Colors.white, height: 1.4),
              ),
              const SizedBox(height: 4),
              Text(
                message.time,
                style: const TextStyle(color: Colors.white60, fontSize: 10),
              ),
            ],
          ),
        ),
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 17,
          backgroundColor: AppColors.surfaceMuted,
          foregroundColor: AppColors.primaryDark,
          child: Text(
            message.sender == 'Place Agent'
                ? '📍'
                : message.sender.characters.first,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12),
          ),
        ),
        const SizedBox(width: 9),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(17),
              border: Border.all(color: AppColors.divider),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 7,
                  children: [
                    Text(
                      message.sender,
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 12,
                      ),
                    ),
                    if (message.tag != null)
                      _StatusPill(
                        label: message.tag!,
                        color: message.sender == 'Place Agent'
                            ? const Color(0xFFDDF7E8)
                            : const Color(0xFFFFE7C2),
                      ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(message.message, style: const TextStyle(height: 1.45)),
                if (message.translation != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    '→ ${message.translation}',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 11,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ],
                const SizedBox(height: 5),
                Text(
                  message.time,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(99),
      ),
      child: Text(
        label,
        style: const TextStyle(color: AppColors.primaryDark, fontSize: 10),
      ),
    );
  }
}

class _PlanningProgress extends StatelessWidget {
  const _PlanningProgress();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.divider),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'AI agents working…',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          SizedBox(height: 12),
          LinearProgressIndicator(
            minHeight: 7,
            borderRadius: BorderRadius.all(Radius.circular(99)),
          ),
          SizedBox(height: 12),
          Text(
            '🧠 Mood Agent: analyzing group preferences…',
            style: TextStyle(fontSize: 11),
          ),
          SizedBox(height: 5),
          Text(
            '📍 Place Agent: scoring attractions…',
            style: TextStyle(fontSize: 11),
          ),
          SizedBox(height: 5),
          Text(
            '🛣️ Route Agent: optimizing routes…',
            style: TextStyle(fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _GeneratedItineraryCard extends StatelessWidget {
  const _GeneratedItineraryCard({required this.onOpen});

  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onOpen,
      borderRadius: BorderRadius.circular(18),
      child: Ink(
        padding: const EdgeInsets.all(17),
        decoration: BoxDecoration(
          color: AppColors.primaryDark,
          borderRadius: BorderRadius.circular(18),
        ),
        child: const Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '✓  ITINERARY GENERATED',
                    style: TextStyle(color: Colors.white70, fontSize: 10),
                  ),
                  SizedBox(height: 7),
                  Text(
                    'View full itinerary →',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  SizedBox(height: 3),
                  Text(
                    '3 days · 8 activities · Hotels to select',
                    style: TextStyle(color: Colors.white70, fontSize: 11),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: Colors.white),
          ],
        ),
      ),
    );
  }
}

class _MessageComposer extends StatelessWidget {
  const _MessageComposer({
    required this.controller,
    required this.hint,
    required this.onSend,
  });

  final TextEditingController controller;
  final String hint;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.divider)),
      ),
      child: SafeArea(
        top: false,
        bottom: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 3,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: InputDecoration(
                  hintText: hint,
                  border: InputBorder.none,
                ),
              ),
            ),
            const SizedBox(width: 10),
            IconButton.filled(
              onPressed: onSend,
              style: IconButton.styleFrom(
                backgroundColor: AppColors.primaryDark,
                foregroundColor: Colors.white,
                minimumSize: const Size.square(50),
              ),
              icon: const Icon(Icons.send_rounded),
            ),
          ],
        ),
      ),
    );
  }
}
