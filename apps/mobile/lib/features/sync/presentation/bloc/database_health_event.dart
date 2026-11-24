import 'package:equatable/equatable.dart';

abstract class DatabaseHealthEvent extends Equatable {
  const DatabaseHealthEvent();

  @override
  List<Object?> get props => [];
}

class DatabaseHealthCheckRequested extends DatabaseHealthEvent {
  const DatabaseHealthCheckRequested();
}

class DatabaseHealthRotateKeyRequested extends DatabaseHealthEvent {
  const DatabaseHealthRotateKeyRequested();
}

class DatabaseHealthQuarantineRequested extends DatabaseHealthEvent {
  const DatabaseHealthQuarantineRequested();
}

class DatabaseHealthEvictionRequested extends DatabaseHealthEvent {
  final Duration? retentionWindow;

  const DatabaseHealthEvictionRequested({this.retentionWindow});

  @override
  List<Object?> get props => [retentionWindow];
}
