/// Lifecycle synchronization status of an offline-queued attendance event.
enum SyncStatus {
  /// Waiting to be synchronized when internet connectivity is available.
  pendingSync,

  /// Currently being transmitted to the server by the synchronization worker.
  syncing,

  /// Successfully ingested and confirmed by the server-authoritative ledger.
  synced,

  /// Rejected by the server with a permanent domain error (e.g. invalid sequence, deactivated user).
  rejectedPermanent,

  /// Quarantined because an earlier dependent event in the same session failed permanently.
  quarantinedDependentFailure,

  /// Ingested by the server but flagged for supervisor review (e.g. clock drift or stale sync).
  flaggedPendingReview;

  String toDbString() {
    switch (this) {
      case SyncStatus.pendingSync:
        return 'PENDING_SYNC';
      case SyncStatus.syncing:
        return 'SYNCING';
      case SyncStatus.synced:
        return 'SYNCED';
      case SyncStatus.rejectedPermanent:
        return 'REJECTED_PERMANENT';
      case SyncStatus.quarantinedDependentFailure:
        return 'QUARANTINED_DEPENDENT_FAILURE';
      case SyncStatus.flaggedPendingReview:
        return 'FLAGGED_PENDING_REVIEW';
    }
  }

  static SyncStatus fromDbString(String val) {
    switch (val.toUpperCase()) {
      case 'PENDING_SYNC':
      case 'PENDING':
        return SyncStatus.pendingSync;
      case 'SYNCING':
      case 'IN_PROGRESS':
        return SyncStatus.syncing;
      case 'SYNCED':
        return SyncStatus.synced;
      case 'REJECTED_PERMANENT':
      case 'REJECTED':
        return SyncStatus.rejectedPermanent;
      case 'QUARANTINED_DEPENDENT_FAILURE':
        return SyncStatus.quarantinedDependentFailure;
      case 'FLAGGED_PENDING_REVIEW':
        return SyncStatus.flaggedPendingReview;
      default:
        return SyncStatus.pendingSync;
    }
  }

  /// Whether this event is currently pending or actively transmitting.
  bool get isPendingOrSyncing =>
      this == SyncStatus.pendingSync || this == SyncStatus.syncing;

  /// Whether this event reached a final terminal state.
  bool get isTerminal =>
      this == SyncStatus.synced ||
      this == SyncStatus.rejectedPermanent ||
      this == SyncStatus.quarantinedDependentFailure ||
      this == SyncStatus.flaggedPendingReview;
}
