import 'failure.dart';

/// Functional Result type encapsulating either success [data] or [failure].
class Result<T> {
  final T? data;
  final Failure? failure;
  final bool isSuccess;

  const Result.success(this.data)
      : failure = null,
        isSuccess = true;

  const Result.failure(this.failure)
      : data = null,
        isSuccess = false;

  bool get isFailure => !isSuccess;
  T get value => data as T;
  Failure get error => failure!;

  R fold<R>(
      R Function(Failure failure) onFailure, R Function(T data) onSuccess) {
    if (isSuccess) {
      return onSuccess(data as T);
    } else {
      return onFailure(
          failure ?? const ServerFailure('Unknown operation failure'));
    }
  }
}
