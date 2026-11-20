import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../core/utils/validators.dart';
import '../../../../shared/widgets/app_button.dart';
import '../../../../shared/widgets/app_text_field.dart';
import '../../../../shared/widgets/error_banner.dart';
import '../bloc/auth_bloc.dart';
import '../bloc/auth_event.dart';
import '../bloc/auth_state.dart';

/// Production-ready enterprise login screen.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _slugController;
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;

  @override
  void initState() {
    super.initState();
    final currentState = context.read<AuthBloc>().state;
    String initialSlug = '';
    String initialEmail = '';

    if (currentState is Unauthenticated) {
      initialSlug = currentState.savedTenantSlug ?? '';
      initialEmail = currentState.savedEmail ?? '';
    }

    _slugController = TextEditingController(text: initialSlug);
    _emailController = TextEditingController(text: initialEmail);
    _passwordController = TextEditingController();
  }

  @override
  void dispose() {
    _slugController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _onSignInPressed() {
    if (_formKey.currentState?.validate() ?? false) {
      FocusScope.of(context).unfocus();
      context.read<AuthBloc>().add(
            LoginSubmitted(
              email: _emailController.text.trim(),
              password: _passwordController.text,
              tenantSlug: _slugController.text.trim(),
            ),
          );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: BlocConsumer<AuthBloc, AuthState>(
          listener: (context, state) {
            if (state is Authenticated) {
              context.go('/home');
            }
          },
          builder: (context, state) {
            final isLoading = state is AuthLoading;
            final errorMessage =
                state is Unauthenticated ? state.errorMessage : null;
            final infoMessage =
                state is Unauthenticated ? state.infoMessage : null;

            return Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(
                    horizontal: 24.0, vertical: 24.0),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 440),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _buildHeader(),
                        const SizedBox(height: 32),
                        if (errorMessage != null) ...[
                          ErrorBanner(message: errorMessage),
                          const SizedBox(height: 20),
                        ] else if (infoMessage != null) ...[
                          ErrorBanner(message: infoMessage, isWarning: true),
                          const SizedBox(height: 20),
                        ],
                        AppTextField(
                          label: 'Company Workspace Code',
                          hintText: 'e.g. acme-corp',
                          controller: _slugController,
                          prefixIcon: Icons.business_rounded,
                          validator: Validators.validateTenantSlug,
                          enabled: !isLoading,
                          textInputAction: TextInputAction.next,
                        ),
                        const SizedBox(height: 18),
                        AppTextField(
                          label: 'Work Email Address',
                          hintText: 'name@company.com',
                          controller: _emailController,
                          prefixIcon: Icons.email_outlined,
                          keyboardType: TextInputType.emailAddress,
                          validator: Validators.validateEmail,
                          enabled: !isLoading,
                          textInputAction: TextInputAction.next,
                        ),
                        const SizedBox(height: 18),
                        AppTextField(
                          label: 'Password',
                          hintText: 'Enter your password',
                          controller: _passwordController,
                          isPassword: true,
                          prefixIcon: Icons.lock_outline_rounded,
                          validator: Validators.validatePassword,
                          enabled: !isLoading,
                          textInputAction: TextInputAction.done,
                        ),
                        const SizedBox(height: 28),
                        AppButton(
                          text: 'Sign In to Workspace',
                          isLoading: isLoading,
                          onPressed: isLoading ? null : _onSignInPressed,
                        ),
                        const SizedBox(height: 32),
                        _buildSecurityFooter(),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            color: AppColors.primaryLight,
            borderRadius: AppRadius.mdBorderRadius,
          ),
          child: const Icon(
            Icons.fingerprint_rounded,
            size: 32,
            color: AppColors.primary,
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'Sign in to UPOSTIT',
          style: AppTypography.displayMedium,
        ),
        const SizedBox(height: 6),
        Text(
          'Enter your corporate workspace credentials to access your attendance profile.',
          style: AppTypography.bodyMedium,
        ),
      ],
    );
  }

  Widget _buildSecurityFooter() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.shield_outlined, size: 16, color: AppColors.textMuted),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            'Protected by Platform Key Vault & TLS 1.3',
            style: AppTypography.bodySmall,
          ),
        ),
      ],
    );
  }
}
