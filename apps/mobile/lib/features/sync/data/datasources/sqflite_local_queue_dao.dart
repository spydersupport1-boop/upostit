import 'dart:convert';
import 'package:sqflite_sqlcipher/sqflite.dart';
import 'package:uuid/uuid.dart';
import '../../../../core/errors/app_exception.dart';
import '../../../attendance/domain/entities/attendance_event.dart';
import '../../domain/entities/local_queue_item.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';
import '../../domain/entities/sync_queue_summary.dart';
import '../../domain/entities/sync_status.dart';
import '../../domain/repositories/local_queue_dao.dart';
import '../models/local_queue_item_model.dart';
import 'local_queue_database.dart';

/// SQLite implementation of [LocalQueueDao] backed by [LocalQueueDatabase].
class SqfliteLocalQueueDao implements LocalQueueDao {
  static const int maxPendingCapacity = 500;

  final LocalQueueDatabase _database;

  SqfliteLocalQueueDao({required LocalQueueDatabase database})
      : _database = database;

  @override
  Future<LocalQueueItem> insertPendingEvent(LocalQueueItem item) async {
    final db = _database.database;

    return await db.transaction<LocalQueueItem>((txn) async {
      // 1. Enforce 500-event offline queue capacity threshold per account
      // Accounts for all unresolved punches: PENDING_SYNC, SYNCING, and QUARANTINED_DEPENDENT_FAILURE
      final countResult = await txn.rawQuery(
        '''
        SELECT COUNT(*) AS unresolved_count 
        FROM ${LocalQueueDatabase.queueTable} 
        WHERE tenant_id = ? AND user_id = ? 
          AND sync_status IN (?, ?, ?)
        ''',
        [
          item.tenantId,
          item.userId,
          SyncStatus.pendingSync.toDbString(),
          SyncStatus.syncing.toDbString(),
          SyncStatus.quarantinedDependentFailure.toDbString(),
        ],
      );

      final currentUnresolved = Sqflite.firstIntValue(countResult) ?? 0;
      if (currentUnresolved >= maxPendingCapacity) {
        throw const QueueCapacityExceededException(
          'Offline queue capacity of $maxPendingCapacity unresolved events reached. '
          'Cannot record additional attendance punches until pending or quarantined '
          'records are synchronized or resolved. Existing records are preserved.',
        );
      }

      // 2. Calculate strictly monotonic sequence number within this user's queue
      final maxSeqResult = await txn.rawQuery(
        '''
        SELECT COALESCE(MAX(sequence_number), 0) AS max_seq 
        FROM ${LocalQueueDatabase.queueTable} 
        WHERE tenant_id = ? AND user_id = ?
        ''',
        [item.tenantId, item.userId],
      );

      final nextSequence = (Sqflite.firstIntValue(maxSeqResult) ?? 0) + 1;

      // 3. Establish attendance session identity for session-aware quarantine
      String assignedSessionId = item.sessionId ?? '';
      if (assignedSessionId.isEmpty) {
        if (item.eventType == AttendanceEventType.checkIn) {
          assignedSessionId = 'sess_${item.localId}';
        } else {
          // Inherit the session ID of the latest check-in for this user
          final latestCheckIn = await txn.rawQuery(
            '''
            SELECT session_id, local_id 
            FROM ${LocalQueueDatabase.queueTable} 
            WHERE tenant_id = ? AND user_id = ? AND event_type = ?
            ORDER BY sequence_number DESC 
            LIMIT 1
            ''',
            [
              item.tenantId,
              item.userId,
              AttendanceEventType.checkIn.toBackendString(),
            ],
          );
          if (latestCheckIn.isNotEmpty) {
            assignedSessionId =
                (latestCheckIn.first['session_id'] as String?) ??
                    'sess_${latestCheckIn.first['local_id']}';
          } else {
            assignedSessionId = 'sess_${item.localId}';
          }
        }
      }

      final nowUtc = DateTime.now().toUtc();

      final itemToInsert = item.copyWith(
        sessionId: assignedSessionId,
        sequenceNumber: nextSequence,
        syncStatus: SyncStatus.pendingSync,
        createdAt: item.createdAt == DateTime.fromMillisecondsSinceEpoch(0)
            ? nowUtc
            : item.createdAt,
        updatedAt: nowUtc,
      );

      final model = LocalQueueItemModel.fromEntity(itemToInsert);

      await txn.insert(
        LocalQueueDatabase.queueTable,
        model.toRow(),
        conflictAlgorithm: ConflictAlgorithm.abort,
      );

      return itemToInsert;
    });
  }

  @override
  Future<List<LocalQueueItem>> getPendingEventsFifo({
    required String tenantId,
    required String userId,
    int limit = 50,
  }) async {
    final db = _database.database;
    final rows = await db.query(
      LocalQueueDatabase.queueTable,
      where: 'tenant_id = ? AND user_id = ? AND sync_status = ?',
      whereArgs: [tenantId, userId, SyncStatus.pendingSync.toDbString()],
      orderBy: 'sequence_number ASC, device_reported_at ASC',
      limit: limit,
    );

    return rows.map((r) => LocalQueueItemModel.fromRow(r)).toList();
  }

  @override
  Future<LocalQueueItem?> getEventById(String localId) async {
    final db = _database.database;
    final rows = await db.query(
      LocalQueueDatabase.queueTable,
      where: 'local_id = ?',
      whereArgs: [localId],
      limit: 1,
    );

    if (rows.isEmpty) return null;
    return LocalQueueItemModel.fromRow(rows.first);
  }

  @override
  Future<LocalQueueItem?> getEventByIdempotencyKey(
      String idempotencyKey) async {
    final db = _database.database;
    final rows = await db.query(
      LocalQueueDatabase.queueTable,
      where: 'idempotency_key = ?',
      whereArgs: [idempotencyKey],
      limit: 1,
    );

    if (rows.isEmpty) return null;
    return LocalQueueItemModel.fromRow(rows.first);
  }

  @override
  Future<void> updateSyncStatus({
    required String localId,
    required SyncStatus status,
    String? serverEventId,
    String? errorMessage,
    int? statusCode,
  }) async {
    final db = _database.database;
    final nowUtc = DateTime.now().toUtc().toIso8601String();

    if (status == SyncStatus.syncing) {
      await db.rawUpdate(
        '''
        UPDATE ${LocalQueueDatabase.queueTable}
        SET sync_status = ?,
            last_attempted_at = ?,
            retry_count = retry_count + 1,
            updated_at = ?
        WHERE local_id = ?
        ''',
        [status.toDbString(), nowUtc, nowUtc, localId],
      );
      return;
    }

    final values = <String, dynamic>{
      'sync_status': status.toDbString(),
      'updated_at': nowUtc,
    };
    if (serverEventId != null) {
      values['server_event_id'] = serverEventId;
    }
    if (errorMessage != null) {
      values['last_error_message'] = errorMessage;
    }
    if (statusCode != null) {
      values['last_error_status_code'] = statusCode;
    }

    await db.update(
      LocalQueueDatabase.queueTable,
      values,
      where: 'local_id = ?',
      whereArgs: [localId],
    );
  }

  @override
  Future<void> markPermanentlyRejected({
    required String localId,
    required String errorMessage,
    int? statusCode,
  }) async {
    await updateSyncStatus(
      localId: localId,
      status: SyncStatus.rejectedPermanent,
      errorMessage: errorMessage,
      statusCode: statusCode,
    );
  }

  @override
  Future<int> quarantineDependentEvents({
    required String tenantId,
    required String userId,
    required String conflictBundleId,
    required String fromLocalId,
  }) async {
    final db = _database.database;

    return await db.transaction<int>((txn) async {
      // 1. Fetch the failed item to determine its sequence_number and session_id
      final rows = await txn.query(
        LocalQueueDatabase.queueTable,
        columns: ['sequence_number', 'session_id', 'event_type'],
        where: 'local_id = ? AND tenant_id = ? AND user_id = ?',
        whereArgs: [fromLocalId, tenantId, userId],
        limit: 1,
      );

      if (rows.isEmpty) return 0;
      final failedSeq = (rows.first['sequence_number'] as num).toInt();
      final failedSessionId = rows.first['session_id'] as String?;
      final nowUtc = DateTime.now().toUtc().toIso8601String();

      // 2. Quarantine ONLY dependent events belonging to the EXACT SAME session
      final int affectedCount;
      if (failedSessionId != null && failedSessionId.isNotEmpty) {
        affectedCount = await txn.rawUpdate(
          '''
          UPDATE ${LocalQueueDatabase.queueTable}
          SET sync_status = ?,
              conflict_bundle_id = ?,
              updated_at = ?
          WHERE tenant_id = ? 
            AND user_id = ? 
            AND session_id = ?
            AND sequence_number > ?
            AND sync_status IN (?, ?)
          ''',
          [
            SyncStatus.quarantinedDependentFailure.toDbString(),
            conflictBundleId,
            nowUtc,
            tenantId,
            userId,
            failedSessionId,
            failedSeq,
            SyncStatus.pendingSync.toDbString(),
            SyncStatus.syncing.toDbString(),
          ],
        );
      } else {
        // Fallback: If session_id was not set, walk subsequent events in order
        // and quarantine only until the next CHECK_IN (which begins a new independent shift)
        final subsequentRows = await txn.query(
          LocalQueueDatabase.queueTable,
          columns: ['local_id', 'event_type', 'sequence_number'],
          where: '''
            tenant_id = ? AND user_id = ? 
            AND sequence_number > ? 
            AND sync_status IN (?, ?)
          ''',
          whereArgs: [
            tenantId,
            userId,
            failedSeq,
            SyncStatus.pendingSync.toDbString(),
            SyncStatus.syncing.toDbString(),
          ],
          orderBy: 'sequence_number ASC',
        );

        final toQuarantineIds = <String>[];
        for (final row in subsequentRows) {
          final eventTypeStr = row['event_type'] as String;
          if (eventTypeStr == AttendanceEventType.checkIn.toBackendString()) {
            // New independent shift / session boundary reached: stop quarantine
            break;
          }
          toQuarantineIds.add(row['local_id'] as String);
          if (eventTypeStr == AttendanceEventType.checkOut.toBackendString()) {
            // End of failed session
            break;
          }
        }

        if (toQuarantineIds.isEmpty) return 0;

        final placeholders = List.filled(toQuarantineIds.length, '?').join(',');
        affectedCount = await txn.rawUpdate(
          '''
          UPDATE ${LocalQueueDatabase.queueTable}
          SET sync_status = ?,
              conflict_bundle_id = ?,
              updated_at = ?
          WHERE local_id IN ($placeholders)
          ''',
          [
            SyncStatus.quarantinedDependentFailure.toDbString(),
            conflictBundleId,
            nowUtc,
            ...toQuarantineIds,
          ],
        );
      }

      // Update the failed item itself with the conflict_bundle_id
      await txn.update(
        LocalQueueDatabase.queueTable,
        {
          'conflict_bundle_id': conflictBundleId,
          'updated_at': nowUtc,
        },
        where: 'local_id = ?',
        whereArgs: [fromLocalId],
      );

      return affectedCount;
    });
  }

  @override
  Future<int> getUnresolvedCount({
    required String tenantId,
    required String userId,
  }) async {
    final db = _database.database;
    final countResult = await db.rawQuery(
      '''
      SELECT COUNT(*) AS unresolved_count 
      FROM ${LocalQueueDatabase.queueTable} 
      WHERE tenant_id = ? AND user_id = ? 
        AND sync_status IN (?, ?, ?)
      ''',
      [
        tenantId,
        userId,
        SyncStatus.pendingSync.toDbString(),
        SyncStatus.syncing.toDbString(),
        SyncStatus.quarantinedDependentFailure.toDbString(),
      ],
    );

    return Sqflite.firstIntValue(countResult) ?? 0;
  }

  @override
  Future<int> getPendingCount({
    required String tenantId,
    required String userId,
  }) async {
    final db = _database.database;
    final countResult = await db.rawQuery(
      '''
      SELECT COUNT(*) AS pending_count 
      FROM ${LocalQueueDatabase.queueTable} 
      WHERE tenant_id = ? AND user_id = ? 
        AND sync_status IN (?, ?)
      ''',
      [
        tenantId,
        userId,
        SyncStatus.pendingSync.toDbString(),
        SyncStatus.syncing.toDbString(),
      ],
    );

    return Sqflite.firstIntValue(countResult) ?? 0;
  }

  @override
  Future<SyncQueueSummary> getQueueSummary({
    required String tenantId,
    required String userId,
  }) async {
    final db = _database.database;
    final rows = await db.rawQuery(
      '''
      SELECT sync_status, COUNT(*) AS status_count
      FROM ${LocalQueueDatabase.queueTable}
      WHERE tenant_id = ? AND user_id = ?
      GROUP BY sync_status
      ''',
      [tenantId, userId],
    );

    int pending = 0;
    int syncing = 0;
    int synced = 0;
    int rejected = 0;
    int quarantined = 0;
    int flagged = 0;

    for (final row in rows) {
      final statusStr = row['sync_status'] as String? ?? '';
      final count = (row['status_count'] as num?)?.toInt() ?? 0;
      final status = SyncStatus.fromDbString(statusStr);
      switch (status) {
        case SyncStatus.pendingSync:
          pending += count;
          break;
        case SyncStatus.syncing:
          syncing += count;
          break;
        case SyncStatus.synced:
          synced += count;
          break;
        case SyncStatus.rejectedPermanent:
          rejected += count;
          break;
        case SyncStatus.quarantinedDependentFailure:
          quarantined += count;
          break;
        case SyncStatus.flaggedPendingReview:
          flagged += count;
          break;
      }
    }

    final lastSyncedRow = await db.rawQuery(
      '''
      SELECT updated_at FROM ${LocalQueueDatabase.queueTable}
      WHERE tenant_id = ? AND user_id = ? AND sync_status = ?
      ORDER BY updated_at DESC LIMIT 1
      ''',
      [tenantId, userId, SyncStatus.synced.toDbString()],
    );

    DateTime? lastSyncedAt;
    if (lastSyncedRow.isNotEmpty && lastSyncedRow.first['updated_at'] != null) {
      try {
        lastSyncedAt =
            DateTime.parse(lastSyncedRow.first['updated_at'] as String);
      } catch (_) {}
    }

    return SyncQueueSummary(
      pendingCount: pending,
      syncingCount: syncing,
      syncedCount: synced,
      permanentlyRejectedCount: rejected,
      quarantinedCount: quarantined,
      flaggedCount: flagged,
      lastSyncedAt: lastSyncedAt,
    );
  }

  @override
  Future<List<LocalQueueItem>> getHistoryEvents({
    required String tenantId,
    required String userId,
    int limit = 50,
  }) async {
    final db = _database.database;
    final rows = await db.query(
      LocalQueueDatabase.queueTable,
      where: 'tenant_id = ? AND user_id = ?',
      whereArgs: [tenantId, userId],
      orderBy: 'device_reported_at DESC',
      limit: limit,
    );

    return rows.map((r) => LocalQueueItemModel.fromRow(r)).toList();
  }

  @override
  Future<int> deleteSyncedEventsOlderThan({required Duration age}) async {
    final db = _database.database;
    final threshold = DateTime.now().toUtc().subtract(age).toIso8601String();

    return await db.delete(
      LocalQueueDatabase.queueTable,
      where: 'sync_status = ? AND updated_at < ?',
      whereArgs: [SyncStatus.synced.toDbString(), threshold],
    );
  }

  @override
  Future<int> resetZombieSyncingItems({
    Duration timeout = const Duration(seconds: 120),
  }) async {
    final db = _database.database;
    final threshold =
        DateTime.now().toUtc().subtract(timeout).toIso8601String();
    final nowUtc = DateTime.now().toUtc().toIso8601String();

    return await db.rawUpdate(
      '''
      UPDATE ${LocalQueueDatabase.queueTable}
      SET sync_status = ?,
          updated_at = ?
      WHERE sync_status = ? AND (last_attempted_at IS NULL OR last_attempted_at < ?)
      ''',
      [
        SyncStatus.pendingSync.toDbString(),
        nowUtc,
        SyncStatus.syncing.toDbString(),
        threshold,
      ],
    );
  }

  @override
  Future<List<OfflineSequenceConflictBundle>> getConflictBundles({
    required String tenantId,
    required String userId,
  }) async {
    final db = _database.database;
    final nowUtc = DateTime.now().toUtc().toIso8601String();

    // 1. Fetch all permanently rejected events for this user
    final rejectedRows = await db.query(
      LocalQueueDatabase.queueTable,
      where: 'tenant_id = ? AND user_id = ? AND sync_status = ?',
      whereArgs: [tenantId, userId, SyncStatus.rejectedPermanent.toDbString()],
      orderBy: 'sequence_number ASC, device_reported_at ASC',
    );

    if (rejectedRows.isEmpty) return [];

    final List<OfflineSequenceConflictBundle> bundles = [];

    for (final rejRow in rejectedRows) {
      final primaryItem = LocalQueueItemModel.fromRow(rejRow);
      String bundleId = primaryItem.conflictBundleId ?? '';

      // If bundleId is not set or empty, assign a deterministic stable UUID v4
      if (bundleId.isEmpty) {
        bundleId = const Uuid().v4();
        await db.update(
          LocalQueueDatabase.queueTable,
          {'conflict_bundle_id': bundleId, 'updated_at': nowUtc},
          where: 'local_id = ?',
          whereArgs: [primaryItem.localId],
        );
      }

      // Fetch dependent quarantined events belonging to this exact session / sequence
      List<Map<String, dynamic>> depRows;
      if (primaryItem.sessionId != null && primaryItem.sessionId!.isNotEmpty) {
        depRows = await db.query(
          LocalQueueDatabase.queueTable,
          where: '''
            tenant_id = ? AND user_id = ? 
            AND session_id = ? 
            AND sequence_number > ?
            AND sync_status = ?
          ''',
          whereArgs: [
            tenantId,
            userId,
            primaryItem.sessionId,
            primaryItem.sequenceNumber,
            SyncStatus.quarantinedDependentFailure.toDbString(),
          ],
          orderBy: 'sequence_number ASC, device_reported_at ASC',
        );
      } else {
        // Fallback: Query by sequence range before next check-in
        final subsequent = await db.query(
          LocalQueueDatabase.queueTable,
          where: '''
            tenant_id = ? AND user_id = ? 
            AND sequence_number > ?
          ''',
          whereArgs: [tenantId, userId, primaryItem.sequenceNumber],
          orderBy: 'sequence_number ASC',
        );

        depRows = [];
        for (final row in subsequent) {
          final type = row['event_type'] as String;
          if (type == AttendanceEventType.checkIn.toBackendString()) break;
          if (row['sync_status'] ==
              SyncStatus.quarantinedDependentFailure.toDbString()) {
            depRows.add(row);
          }
          if (type == AttendanceEventType.checkOut.toBackendString()) break;
        }
      }

      // Ensure dependent items carry the same conflict_bundle_id
      for (final depRow in depRows) {
        if (depRow['conflict_bundle_id'] != bundleId) {
          await db.update(
            LocalQueueDatabase.queueTable,
            {'conflict_bundle_id': bundleId, 'updated_at': nowUtc},
            where: 'local_id = ?',
            whereArgs: [depRow['local_id']],
          );
        }
      }

      final dependentItems =
          depRows.map((r) => LocalQueueItemModel.fromRow(r)).toList();

      // Check metadata table for previous submission info
      final meta = await getConflictBundleSubmission(bundleId);
      ConflictSubmissionStatus subStatus =
          ConflictSubmissionStatus.notSubmitted;
      String? incidentId;
      String? decision;
      String? decisionReason;
      DateTime? submittedAt;
      DateTime? decidedAt;
      String? notes;

      if (meta != null) {
        incidentId = meta['incident_id'] as String?;
        subStatus = ConflictSubmissionStatus.fromBackendString(
            meta['status'] as String?);
        decision = meta['decision'] as String?;
        decisionReason = meta['decision_reason'] as String?;
        notes = meta['employee_notes'] as String?;
        if (meta['submitted_at'] != null) {
          try {
            submittedAt = DateTime.parse(meta['submitted_at'] as String);
          } catch (_) {}
        }
        if (meta['decided_at'] != null) {
          try {
            decidedAt = DateTime.parse(meta['decided_at'] as String);
          } catch (_) {}
        }
      }

      bundles.add(
        OfflineSequenceConflictBundle(
          bundleId: bundleId,
          sessionId: primaryItem.sessionId,
          tenantId: tenantId,
          userId: userId,
          primaryRejectedEvent: primaryItem,
          dependentEvents: dependentItems,
          employeeNotes: notes,
          submissionStatus: subStatus,
          incidentId: incidentId,
          supervisorDecision: decision,
          supervisorDecisionReason: decisionReason,
          submittedAt: submittedAt,
          decidedAt: decidedAt,
        ),
      );
    }

    return bundles;
  }

  @override
  Future<void> saveConflictBundleSubmission({
    required String bundleId,
    required String incidentId,
    required String status,
    String? decision,
    String? decisionReason,
    DateTime? submittedAt,
    DateTime? decidedAt,
    String? employeeNotes,
  }) async {
    final db = _database.database;
    final key = 'conflict_submission_$bundleId';
    final payload = jsonEncode({
      'incident_id': incidentId,
      'status': status,
      'decision': decision,
      'decision_reason': decisionReason,
      'submitted_at': submittedAt?.toUtc().toIso8601String() ??
          DateTime.now().toUtc().toIso8601String(),
      'decided_at': decidedAt?.toUtc().toIso8601String(),
      if (employeeNotes != null) 'employee_notes': employeeNotes,
    });

    await db.insert(
      LocalQueueDatabase.metadataTable,
      {'key': key, 'value': payload},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );

    // If supervisor has APPROVED this incident, update local events to synced
    if (status.toUpperCase() == 'APPROVED') {
      await markConflictBundleResolved(
        bundleId: bundleId,
        status: SyncStatus.synced,
      );
    }
  }

  @override
  Future<Map<String, dynamic>?> getConflictBundleSubmission(
      String bundleId) async {
    final db = _database.database;
    final rows = await db.query(
      LocalQueueDatabase.metadataTable,
      where: 'key = ?',
      whereArgs: ['conflict_submission_$bundleId'],
      limit: 1,
    );

    if (rows.isEmpty) return null;
    try {
      final val = rows.first['value'] as String;
      return jsonDecode(val) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> markConflictBundleResolved({
    required String bundleId,
    required SyncStatus status,
  }) async {
    final db = _database.database;
    final nowUtc = DateTime.now().toUtc().toIso8601String();

    await db.update(
      LocalQueueDatabase.queueTable,
      {
        'sync_status': status.toDbString(),
        'updated_at': nowUtc,
      },
      where: 'conflict_bundle_id = ?',
      whereArgs: [bundleId],
    );
  }
}
