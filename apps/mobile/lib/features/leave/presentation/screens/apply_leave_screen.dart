import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/leave_type.dart';
import '../bloc/leave_bloc.dart';
import '../bloc/leave_event.dart';
import '../bloc/leave_state.dart';

class ApplyLeaveScreen extends StatefulWidget {
  const ApplyLeaveScreen({super.key});

  @override
  State<ApplyLeaveScreen> createState() => _ApplyLeaveScreenState();
}

class _ApplyLeaveScreenState extends State<ApplyLeaveScreen> {
  final _formKey = GlobalKey<FormState>();
  final _reasonController = TextEditingController();

  LeaveType? _selectedType;
  DateTime _startDate = DateTime.now().add(const Duration(days: 1));
  DateTime _endDate = DateTime.now().add(const Duration(days: 1));
  bool _isHalfDay = false;
  String _halfDayPeriod = 'FIRST_HALF';

  @override
  void initState() {
    super.initState();
    final state = context.read<LeaveBloc>().state;
    if (state.leaveTypes.isNotEmpty) {
      _selectedType = state.leaveTypes.first;
    }
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  double get _calculatedDays {
    if (_isHalfDay) return 0.5;
    final diff = _endDate.difference(_startDate).inDays;
    return (diff >= 0 ? diff + 1 : 1).toDouble();
  }

  Future<void> _pickDateRange(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: now.subtract(const Duration(days: 30)),
      lastDate: now.add(const Duration(days: 365)),
      initialDateRange: DateTimeRange(start: _startDate, end: _endDate),
    );

    if (picked != null) {
      setState(() {
        _startDate = picked.start;
        _endDate = picked.end;
      });
    }
  }

  Future<void> _pickSingleDate(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _startDate,
      firstDate: now.subtract(const Duration(days: 30)),
      lastDate: now.add(const Duration(days: 365)),
    );

    if (picked != null) {
      setState(() {
        _startDate = picked;
        _endDate = picked;
      });
    }
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedType == null) return;

    final startStr = DateFormat('yyyy-MM-dd').format(_startDate);
    final endStr = DateFormat('yyyy-MM-dd').format(_endDate);

    context.read<LeaveBloc>().add(
          LeaveApplicationSubmitted(
            leaveTypeId: _selectedType!.id,
            startDate: startStr,
            endDate: endStr,
            isHalfDay: _isHalfDay,
            halfDayPeriod: _isHalfDay ? _halfDayPeriod : null,
            reason: _reasonController.text.trim(),
          ),
        );
  }

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('EEE, MMM d, yyyy');

    return Scaffold(
      appBar: AppBar(
        title: const Text('Apply for Leave'),
      ),
      body: BlocConsumer<LeaveBloc, LeaveState>(
        listener: (context, state) {
          if (state.errorMessage != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(state.errorMessage!),
                backgroundColor: AppColors.error,
              ),
            );
            context.read<LeaveBloc>().add(const LeaveNoticesCleared());
          } else if (state.successNotice != null &&
              state.lastSubmittedRequest != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(state.successNotice!),
                backgroundColor: AppColors.success,
              ),
            );
            context.read<LeaveBloc>().add(const LeaveNoticesCleared());
            Navigator.of(context).pop();
          }
        },
        builder: (context, state) {
          final types = state.leaveTypes;
          if (_selectedType == null && types.isNotEmpty) {
            _selectedType = types.first;
          }

          final balance = state.balances
              .where((b) => b.leaveTypeId == _selectedType?.id)
              .firstOrNull;

          return SingleChildScrollView(
            padding: AppSpacing.pagePadding,
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Leave Type Selector
                  Text('Leave Type', style: AppTypography.headingMedium),
                  const SizedBox(height: AppSpacing.xs),
                  DropdownButtonFormField<LeaveType>(
                    initialValue: _selectedType,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm + 4,
                      ),
                    ),
                    items: types.map((type) {
                      return DropdownMenuItem<LeaveType>(
                        value: type,
                        child: Text('${type.name} (${type.code})'),
                      );
                    }).toList(),
                    onChanged: (val) {
                      setState(() {
                        _selectedType = val;
                        if (_selectedType?.allowHalfDay == false) {
                          _isHalfDay = false;
                        }
                      });
                    },
                    validator: (val) =>
                        val == null ? 'Please select a leave category' : null,
                  ),
                  if (balance != null) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Row(
                      children: [
                        const Icon(
                          Icons.account_balance_wallet_outlined,
                          size: 14,
                          color: AppColors.primary,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Text(
                          'Available Balance: ${balance.availableBalance.toStringAsFixed(1)} days',
                          style: AppTypography.caption.copyWith(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),

                  // Half-Day Toggle (if allowed by selected type)
                  if (_selectedType?.allowHalfDay ?? true) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.xs,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.borderLight),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Half-day Leave',
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 14,
                                ),
                              ),
                              Text(
                                'Apply for half working day (0.5d)',
                                style: AppTypography.caption.copyWith(
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                          Switch(
                            value: _isHalfDay,
                            activeTrackColor: AppColors.primary,
                            onChanged: (val) {
                              setState(() {
                                _isHalfDay = val;
                                if (_isHalfDay) {
                                  _endDate = _startDate;
                                }
                              });
                            },
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                  ],

                  // If Half Day: Period selection
                  if (_isHalfDay) ...[
                    Text('Half-Day Session',
                        style: AppTypography.headingMedium),
                    const SizedBox(height: AppSpacing.xs),
                    Row(
                      children: [
                        Expanded(
                          child: ChoiceChip(
                            label: const Center(
                                child: Text('First Half (Morning)')),
                            selected: _halfDayPeriod == 'FIRST_HALF',
                            selectedColor: AppColors.primaryLight,
                            onSelected: (selected) {
                              if (selected) {
                                setState(() => _halfDayPeriod = 'FIRST_HALF');
                              }
                            },
                          ),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: ChoiceChip(
                            label: const Center(
                                child: Text('Second Half (Afternoon)')),
                            selected: _halfDayPeriod == 'SECOND_HALF',
                            selectedColor: AppColors.primaryLight,
                            onSelected: (selected) {
                              if (selected) {
                                setState(() => _halfDayPeriod = 'SECOND_HALF');
                              }
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.lg),
                  ],

                  // Date Selection
                  Text(
                    _isHalfDay ? 'Date' : 'Leave Dates',
                    style: AppTypography.headingMedium,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  InkWell(
                    onTap: () => _isHalfDay
                        ? _pickSingleDate(context)
                        : _pickDateRange(context),
                    borderRadius: AppRadius.mdBorderRadius,
                    child: Container(
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.calendar_month,
                            color: AppColors.primary,
                            size: 20,
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              _isHalfDay
                                  ? dateFormat.format(_startDate)
                                  : '${dateFormat.format(_startDate)}  →  ${dateFormat.format(_endDate)}',
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const Icon(
                            Icons.edit_calendar,
                            color: AppColors.textMuted,
                            size: 18,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),

                  // Reason field
                  Text('Reason for Leave', style: AppTypography.headingMedium),
                  const SizedBox(height: AppSpacing.xs),
                  TextFormField(
                    controller: _reasonController,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      hintText: 'Please describe the reason for your leave...',
                      border: OutlineInputBorder(),
                    ),
                    validator: (val) {
                      if (val == null || val.trim().isEmpty) {
                        return 'Reason is required';
                      }
                      if (val.trim().length < 3) {
                        return 'Reason must be at least 3 characters';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: AppSpacing.xl),

                  // Pre-submission summary banner
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    decoration: BoxDecoration(
                      color: AppColors.primaryLight,
                      borderRadius: AppRadius.mdBorderRadius,
                      border: Border.all(
                        color: AppColors.primary.withValues(alpha: 0.2),
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Total Leave Duration',
                              style: TextStyle(
                                fontSize: 12,
                                color: AppColors.textSecondary,
                              ),
                            ),
                            Text(
                              '${_calculatedDays % 1 == 0 ? _calculatedDays.toInt() : _calculatedDays} ${_calculatedDays == 1 ? 'day' : 'days'}',
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w700,
                                color: AppColors.primaryDark,
                              ),
                            ),
                          ],
                        ),
                        if (_selectedType != null)
                          Text(
                            _selectedType!.isPaid
                                ? 'Paid Leave'
                                : 'Unpaid Leave',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: _selectedType!.isPaid
                                  ? AppColors.success
                                  : AppColors.warning,
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xl),

                  // Submit button
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton(
                      onPressed: state.isSubmitting ? null : _submit,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: AppRadius.mdBorderRadius,
                        ),
                      ),
                      child: state.isSubmitting
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor:
                                    AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            )
                          : const Text(
                              'Submit Leave Application',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
