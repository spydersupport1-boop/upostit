import 'package:equatable/equatable.dart';
import '../../domain/entities/employee.dart';

abstract class ProfileState extends Equatable {
  const ProfileState();

  @override
  List<Object?> get props => [];
}

class ProfileInitial extends ProfileState {
  const ProfileInitial();
}

class ProfileLoading extends ProfileState {
  const ProfileLoading();
}

class ProfileLoaded extends ProfileState {
  final Employee?
      employee; // Nullable to handle administrative/owner users without employee record
  final bool hasLinkedEmployee;

  const ProfileLoaded({
    this.employee,
    this.hasLinkedEmployee = true,
  });

  @override
  List<Object?> get props => [employee, hasLinkedEmployee];
}

class ProfileError extends ProfileState {
  final String message;

  const ProfileError(this.message);

  @override
  List<Object?> get props => [message];
}
