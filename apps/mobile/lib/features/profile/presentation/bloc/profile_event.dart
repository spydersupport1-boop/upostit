import 'package:equatable/equatable.dart';

abstract class ProfileEvent extends Equatable {
  const ProfileEvent();

  @override
  List<Object?> get props => [];
}

class FetchProfileRequested extends ProfileEvent {
  const FetchProfileRequested();
}

class ProfileRefreshed extends ProfileEvent {
  const ProfileRefreshed();
}
