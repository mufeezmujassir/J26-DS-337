import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import 'widgets/auth_scaffold.dart';

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _formKey = GlobalKey<FormState>();

  void _continue() {
    if (_formKey.currentState?.validate() ?? false) {
      FocusScope.of(context).unfocus();
      context.go('/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScaffold(
      title: 'Welcome to Wandaraya',
      subtitle: 'Sign in to begin your next Sri Lankan adventure.',
      onBack: () => context.go('/onboarding'),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              keyboardType: TextInputType.phone,
              textInputAction: TextInputAction.done,
              autofillHints: const [AutofillHints.telephoneNumber],
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'Phone number',
                hintText: '77 123 4567',
                prefixIcon: _CountryCode(),
              ),
              validator: (value) {
                if (value == null || value.trim().length < 9) {
                  return 'Enter a valid phone number';
                }
                return null;
              },
              onFieldSubmitted: (_) => _continue(),
            ),
            const SizedBox(height: 12),
            const Text(
              'We’ll send a secure verification code to confirm your number. Standard message rates may apply.',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 22),
            ElevatedButton(
              onPressed: _continue,
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text('Continue'),
                  SizedBox(width: 9),
                  Icon(Icons.arrow_forward_rounded, size: 20),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const AuthDivider(),
            const SizedBox(height: 18),
            SocialAuthButton(
              label: 'Continue with Google',
              leading: const Text(
                'G',
                style: TextStyle(
                  color: Color(0xFF4285F4),
                  fontWeight: FontWeight.w900,
                  fontSize: 18,
                ),
              ),
              onPressed: () => context.go('/home'),
            ),
            const SizedBox(height: 12),
            SocialAuthButton(
              label: 'Continue with Apple',
              leading: const Icon(Icons.apple_rounded, size: 22),
              onPressed: () => context.go('/home'),
            ),
            const SizedBox(height: 30),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'New to Wandaraya?',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
                TextButton(
                  onPressed: () => context.push('/sign-up'),
                  child: const Text(
                    'Create account',
                    style: TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CountryCode extends StatelessWidget {
  const _CountryCode();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(left: 16, right: 10),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('🇱🇰', style: TextStyle(fontSize: 19)),
          SizedBox(width: 7),
          Text('+94', style: TextStyle(fontWeight: FontWeight.w700)),
          SizedBox(width: 7),
          SizedBox(
            height: 22,
            child: VerticalDivider(color: AppColors.divider),
          ),
        ],
      ),
    );
  }
}
