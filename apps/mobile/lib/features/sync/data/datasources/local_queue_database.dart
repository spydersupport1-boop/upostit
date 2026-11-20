import 'package:sqflite_sqlcipher/sqflite.dart';
import '../../../../core/errors/app_exception.dart';
import 'database_key_provider.dart';

/// Manages the encrypted SQLite database for offline attendance queuing.
///
/// Ensures fail-closed security: the database is never opened or created in plaintext
/// if encryption initialization, key retrieval, or metadata verification fails.
class LocalQueueDatabase {
  static const String databaseName = 'upostit_offline_queue.db';
  static const int databaseVersion = 1;
  static const String metadataTable = 'local_storage_metadata';
  static const String queueTable = 'local_attendance_queue';
  static const String expectedEngine = 'SQLCIPHER_PAGE_AES256';

  final DatabaseKeyProvider _keyProvider;
  final DatabaseFactory? _factory;
  final String? _customPath;

  Database? _db;

  LocalQueueDatabase({
    DatabaseKeyProvider? keyProvider,
    DatabaseFactory? factory,
    String? customPath,
  })  : _keyProvider = keyProvider ?? FlutterSecureStorageDatabaseKeyProvider(),
        _factory = factory,
        _customPath = customPath;

  bool get isOpen => _db != null && _db!.isOpen;

  Database get database {
    if (_db == null || !_db!.isOpen) {
      throw const DatabaseEncryptionException(
        'Encrypted local queue database is not open. Call open() first.',
      );
    }
    return _db!;
  }

  /// Opens or creates the encrypted database using AES-256 SQLCipher.
  ///
  /// Throws [DatabaseEncryptionException] if key generation, opening, or metadata
  /// verification fails.
  Future<Database> open() async {
    if (_db != null && _db!.isOpen) {
      return _db!;
    }

    // 1. Resolve database path first
    final String path;
    if (_customPath != null) {
      path = _customPath;
    } else {
      final factory = _factory;
      final String dbDir = factory != null
          ? await factory.getDatabasesPath()
          : await getDatabasesPath();
      path = '$dbDir/$databaseName';
    }

    // 2. Check whether the database file already exists on the filesystem
    final bool dbExists;
    if (path == inMemoryDatabasePath) {
      dbExists = false;
    } else {
      final factory = _factory;
      if (factory != null) {
        dbExists = await factory.databaseExists(path);
      } else {
        dbExists = await databaseExists(path);
      }
    }

    // 3. Obtain key from secure hardware-backed storage (distinguishing new vs existing DB)
    final String key;
    try {
      key = await _keyProvider.getEncryptionKey(databaseExists: dbExists);
      if (key.trim().isEmpty) {
        throw const DatabaseEncryptionException(
          'Failed to obtain database encryption key: key is empty.',
        );
      }
    } catch (e, stackTrace) {
      if (e is DatabaseEncryptionException) rethrow;
      throw DatabaseEncryptionException(
        'Failed to obtain database encryption key from secure storage: $e',
        e,
        stackTrace,
      );
    }

    // 4. Open or initialize database with SQLCipher encryption password
    try {
      final Database db;
      final factory = _factory;
      if (factory != null) {
        db = await factory.openDatabase(
          path,
          options: OpenDatabaseOptions(
            version: databaseVersion,
            singleInstance: false,
            onCreate: _onCreate,
            onUpgrade: _onUpgrade,
          ),
        );
      } else {
        db = await openDatabase(
          path,
          version: databaseVersion,
          password: key,
          singleInstance: false,
          onCreate: _onCreate,
          onUpgrade: _onUpgrade,
        );
      }

      // 5. Validate metadata / encryption engine verification
      final List<Map<String, dynamic>> metaRows = await db.query(
        metadataTable,
        where: 'key = ?',
        whereArgs: ['encryption_engine'],
      );

      if (metaRows.isEmpty || metaRows.first['value'] != expectedEngine) {
        await db.close();
        throw const DatabaseEncryptionException(
          'Database encryption verification failed: missing or invalid engine metadata.',
        );
      }

      _db = db;
      return db;
    } catch (e, stackTrace) {
      if (_db != null && _db!.isOpen) {
        await _db!.close();
        _db = null;
      }
      if (e is DatabaseEncryptionException) rethrow;
      throw DatabaseEncryptionException(
        'Fail-closed: could not securely initialize encrypted local queue database: $e',
        e,
        stackTrace,
      );
    }
  }

  Future<void> _onCreate(Database db, int version) async {
    // 1. Create metadata table
    await db.execute('''
      CREATE TABLE $metadataTable (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
    ''');

    // 2. Insert metadata
    await db.insert(metadataTable, {
      'key': 'encryption_engine',
      'value': expectedEngine,
    });
    await db.insert(metadataTable, {
      'key': 'schema_version',
      'value': version.toString(),
    });
    await db.insert(metadataTable, {
      'key': 'created_at',
      'value': DateTime.now().toUtc().toIso8601String(),
    });
    await db.execute('PRAGMA user_version = $version;');

    // 3. Create offline queue table
    await db.execute('''
      CREATE TABLE $queueTable (
        local_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        session_id TEXT,
        tenant_id TEXT NOT NULL,
        employee_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        device_reported_at TEXT NOT NULL,
        timezone_offset_minutes INTEGER NOT NULL,
        monotonic_boot_time_ms INTEGER NOT NULL,
        boot_session_id TEXT NOT NULL,
        is_reboot_detected INTEGER NOT NULL DEFAULT 0,
        location_id TEXT,
        latitude REAL,
        longitude REAL,
        accuracy_meters REAL,
        wifi_bssid TEXT,
        wifi_ssid TEXT,
        wifi_signal_status TEXT NOT NULL DEFAULT 'AVAILABLE',
        encrypted_payload_blob TEXT,
        applied_policy_version INTEGER NOT NULL DEFAULT 1,
        applied_policy_mode TEXT NOT NULL DEFAULT 'MANUAL',
        device_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        sequence_number INTEGER NOT NULL,
        sync_status TEXT NOT NULL DEFAULT 'PENDING_SYNC',
        conflict_bundle_id TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        last_attempted_at TEXT,
        last_error_message TEXT,
        last_error_status_code INTEGER,
        server_event_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    ''');

    // 4. Performance & FIFO indexes
    await db.execute('''
      CREATE INDEX idx_local_queue_fifo 
      ON $queueTable(tenant_id, user_id, sync_status, sequence_number ASC);
    ''');
    await db.execute('''
      CREATE UNIQUE INDEX idx_local_queue_idempotency 
      ON $queueTable(idempotency_key);
    ''');
    await db.execute('''
      CREATE INDEX idx_local_queue_status 
      ON $queueTable(sync_status);
    ''');
    await db.execute('''
      CREATE INDEX idx_local_queue_sequence 
      ON $queueTable(tenant_id, user_id, sequence_number ASC);
    ''');
    await db.execute('''
      CREATE INDEX idx_local_queue_session 
      ON $queueTable(tenant_id, user_id, session_id);
    ''');
    await db.execute('''
      CREATE INDEX idx_local_queue_created 
      ON $queueTable(tenant_id, user_id, created_at DESC);
    ''');
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Migration logic for future versions
  }

  Future<void> close() async {
    if (_db != null && _db!.isOpen) {
      await _db!.close();
      _db = null;
    }
  }

  Future<void> deleteDb() async {
    await close();
    final String path;
    if (_customPath != null) {
      path = _customPath;
    } else {
      final factory = _factory;
      final String dbDir = factory != null
          ? await factory.getDatabasesPath()
          : await getDatabasesPath();
      path = '$dbDir/$databaseName';
    }
    final factory = _factory;
    if (factory != null) {
      await factory.deleteDatabase(path);
    } else {
      await deleteDatabase(path);
    }
  }
}
