import 'package:flutter_bloc/flutter_bloc.dart';
import '../../domain/usecases/get_profile_usecase.dart';
import 'profile_event.dart';
import 'profile_state.dart';

class ProfileBloc extends Bloc<ProfileEvent, ProfileState> {
  final GetProfileUseCase _getProfileUseCase;

  ProfileBloc({required GetProfileUseCase getProfileUseCase})
      : _getProfileUseCase = getProfileUseCase,
        super(const ProfileInitial()) {
    on<FetchProfileRequested>(_onFetchProfileRequested);
    on<ProfileRefreshed>(_onProfileRefreshed);
  }

  Future<void> _onFetchProfileRequested(
    FetchProfileRequested event,
    Emitter<ProfileState> emit,
  ) async {
    emit(const ProfileLoading());
    await _loadProfile(emit);
  }

  Future<void> _onProfileRefreshed(
    ProfileRefreshed event,
    Emitter<ProfileState> emit,
  ) async {
    await _loadProfile(emit);
  }

  Future<void> _loadProfile(Emitter<ProfileState> emit) async {
    final result = await _getProfileUseCase();

    result.fold(
      (failure) {
        if (failure.statusCode == 404) {
          // Graceful handling: user is logged in as Owner/Admin without linked Employee row
          emit(const ProfileLoaded(employee: null, hasLinkedEmployee: false));
        } else {
          emit(ProfileError(failure.message));
        }
      },
      (employee) {
        emit(ProfileLoaded(employee: employee, hasLinkedEmployee: true));
      },
    );
  }
}
