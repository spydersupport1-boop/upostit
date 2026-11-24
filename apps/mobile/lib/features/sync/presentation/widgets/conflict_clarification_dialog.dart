import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/app_button.dart';

/// Modal dialog allowing employees to provide clarification for ambiguous or conflicting punches.
class ConflictClarificationDialog extends StatefulWidget {
  final String incidentId;
  final String? conflictCode;
  final String? rejectionSummary;
  final String? supervisorReason;
  final bool isSubmitting;
  final void Function(String clarificationNotes) onSubmit;

  const ConflictClarificationDialog({
    super.key,
    required this.incidentId,
    this.conflictCode,
    this.rejectionSummary,
    this.supervisorReason,
    this.isSubmitting = false,
    required this.onSubmit,
  });

  @override
  State<ConflictClarificationDialog> createState() =>
      _ConflictClarificationDialogState();
}

class _ConflictClarificationDialogState
    extends State<ConflictClarificationDialog> {
  late final TextEditingController _controller;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _handleSubmit() {
    final text = _controller.text.trim();
    if (text.length < 3) {
      setState(() {
        _errorText = 'Please provide at least 3 characters of clarification.';
      });
      return;
    }
    setState(() => _errorText = null);
    widget.onSubmit(text);
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
      ),
      backgroundColor: AppColors.surface,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.help_outline,
                    color: AppColors.warning,
                    size: 28,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'Attendance Clarification',
                      style: AppTypography.headingMedium.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              if (widget.conflictCode != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.warning.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    widget.conflictCode!,
                    style: AppTypography.caption.copyWith(
                      color: AppColors.warning,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
              if (widget.rejectionSummary != null) ...[
                Text(
                  'Issue Details:',
                  style: AppTypography.labelMedium.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  widget.rejectionSummary!,
                  style: AppTypography.bodySmall.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
              if (widget.supervisorReason != null) ...[
                Text(
                  'Supervisor Note:',
                  style: AppTypography.labelMedium.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  widget.supervisorReason!,
                  style: AppTypography.bodySmall.copyWith(
                    color: AppColors.textPrimary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
              ],
              Text(
                'Your Clarification:',
                style: AppTypography.labelMedium.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                controller: _controller,
                maxLines: 4,
                maxLength: 1000,
                decoration: InputDecoration(
                  hintText:
                      'Explain what happened (e.g., "Switched to backup phone", "Accidental punch")...',
                  errorText: _errorText,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: widget.isSubmitting
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  AppButton(
                    text: 'Submit Clarification',
                    isLoading: widget.isSubmitting,
                    onPressed: _handleSubmit,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
