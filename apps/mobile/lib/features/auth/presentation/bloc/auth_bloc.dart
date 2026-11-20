import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/storage/secure_storage_service.dart';
import '../../domain/repositories/auth_repository.dart';
import '../../domain/usecases/login_usecase.dart';
import '../../domain/usecases/logout_usecase.dart';
import '../../domain/usecases/restore_session_usecase.dart';
import 'auth_event.dart';
import 'auth_state.dart';

class AuthBloc extends Bloc<AuthEvent, AuthState> {
  final LoginUseCase _loginUseCase;
  final RestoreSessionUseCase _restoreSessionUseCase;
  final LogoutUseCase _logoutUseCase;
  final AuthRepository _authRepository;
  final SecureStorageService _secureStorage;

  AuthBloc({
    required LoginUseCase loginUseCase,
    required RestoreSessionUseCase restoreSessionUseCase,
    required LogoutUseCase logoutUseCase,
    required AuthRepository authRepository,
    required SecureStorageService secureStorage,
  })  : _loginUseCase = loginUseCase,
        _restoreSessionUseCase = restoreSessionUseCase,
        _logoutUseCase = logoutUseCase,
        _authRepository = authRepository,
        _secureStorage = secureStorage,
        super(const AuthInitial()) {
    on<AuthCheckRequested>(_onAuthCheckRequested);
    on<LoginSubmitted>(_onLoginSubmitted);
    on<LogoutRequested>(_onLogoutRequested);
    on<SessionExpiredDetected>(_onSessionExpiredDetected);
  }

  Future<void> _onAuthCheckRequested(
    AuthCheckRequested event,
    Emitter<AuthState> emit,
  ) async {
    emit(const AuthLoading(message: 'Restoring secure session...'));

    final savedSlug = await _secureStorage.getSavedTenantSlug();
    final savedEmail = await _secureStorage.getSavedEmail();

    final restoreResult = await _restoreSessionUseCase();

    await restoreResult.fold(
      (failure) async {
        if (failure is NetworkFailure) {
          // Network issue: preserve token, allow retry
          emit(
            AuthRestoreError(
              message: failure.message,
              isNetworkError: true,
            ),
          );
        } else {
          // No token or token invalid/revoked
          emit(
            Unauthenticated(
              infoMessage: failure is AuthFailure && failure.isSessionExpired
                  ? 'Your session has expired. Please sign in.'
                  : null,
              savedTenantSlug: savedSlug,
              savedEmail: savedEmail,
            ),
          );
        }
      },
      (tokens) async {
        // Tokens successfully rotated; now fetch authenticated user & tenant profile
        final meResult = await _authRepository.getMe();
        meResult.fold(
          (failure) {
            emit(
              Unauthenticated(
                errorMessage: failure.message,
                savedTenantSlug: savedSlug,
                savedEmail: savedEmail,
              ),
            );
          },
          (userProfile) {
            emit(Authenticated(userProfile: userProfile));
          },
        );
      },
    );
  }

  Future<void> _onLoginSubmitted(
    LoginSubmitted event,
    Emitter<AuthState> emit,
  ) async {
    emit(const AuthLoading(message: 'Verifying credentials...'));

    final loginResult = await _loginUseCase(
      email: event.email,
      password: event.password,
      tenantSlug: event.tenantSlug,
    );

    await loginResult.fold(
      (failure) async {
        emit(
          Unauthenticated(
            errorMessage: failure.message,
            savedTenantSlug: event.tenantSlug,
            savedEmail: event.email,
          ),
        );
      },
      (tokens) async {
        final meResult = await _authRepository.getMe();
        meResult.fold(
          (failure) {
            emit(
              Unauthenticated(
                errorMessage:
                    'Authentication succeeded but profile could not be loaded: ${failure.message}',
                savedTenantSlug: event.tenantSlug,
                savedEmail: event.email,
              ),
            );
          },
          (userProfile) {
            emit(Authenticated(userProfile: userProfile));
          },
        );
      },
    );
  }

  Future<void> _onLogoutRequested(
    LogoutRequested event,
    Emitter<AuthState> emit,
  ) async {
    emit(const AuthLoading(message: 'Signing out...'));

    final savedSlug = await _secureStorage.getSavedTenantSlug();
    final savedEmail = await _secureStorage.getSavedEmail();

    final logoutResult = await _logoutUseCase();

    logoutResult.fold(
      (failure) {
        emit(
          Unauthenticated(
            infoMessage: failure.message,
            savedTenantSlug: savedSlug,
            savedEmail: savedEmail,
          ),
        );
      },
      (_) {
        emit(
          Unauthenticated(
            infoMessage: 'You have been signed out successfully.',
            savedTenantSlug: savedSlug,
            savedEmail: savedEmail,
          ),
        );
      },
    );
  }

  Future<void> _onSessionExpiredDetected(
    SessionExpiredDetected event,
    Emitter<AuthState> emit,
  ) async {
    final savedSlug = await _secureStorage.getSavedTenantSlug();
    final savedEmail = await _secureStorage.getSavedEmail();

    emit(
      Unauthenticated(
        errorMessage: event.message,
        savedTenantSlug: savedSlug,
        savedEmail: savedEmail,
      ),
    );
  }
}
