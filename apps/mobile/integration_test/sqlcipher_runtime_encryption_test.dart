import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite_sqlcipher/sqflite.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('SQLCipher Native Runtime Encryption Integration Tests', () {
    testWidgets(
        'proves native SQLCipher page encryption, correct-key reopen, wrong-key failure, and plaintext rejection',
        (WidgetTester tester) async {
      final dbDir = await getDatabasesPath();
      final dbPath = '$dbDir/runtime_sqlcipher_proof.db';
      await deleteDatabase(dbPath);

      const correctKey =
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
      const wrongKey =
          'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210';

      // 1. Create encrypted database with correctKey
      final db = await openDatabase(
        dbPath,
        password: correctKey,
        singleInstance: false,
        version: 1,
        onCreate: (db, version) async {
          await db.execute(
            'CREATE TABLE secret_evidence (id INTEGER PRIMARY KEY, note TEXT NOT NULL);',
          );
          await db.insert('secret_evidence', {
            'id': 1,
            'note': 'confidential_attendance_biometric_evidence',
          });
        },
      );
      expect(db.isOpen, isTrue);
      await db.close();

      // 2. Reopen with correctKey -> must succeed and read encrypted data
      final reopenDb = await openDatabase(
        dbPath,
        password: correctKey,
        singleInstance: false,
        version: 1,
      );
      final rows = await reopenDb.query('secret_evidence');
      expect(rows.length, equals(1));
      expect(
        rows.first['note'],
        equals('confidential_attendance_biometric_evidence'),
      );
      await reopenDb.close();

      // 3. Reopen with wrongKey -> SQLCipher must fail decryption (file is not a database / HMAC failure)
      bool wrongKeyFailed = false;
      try {
        final wrongDb = await openDatabase(
          dbPath,
          password: wrongKey,
          singleInstance: false,
          version: 1,
        );
        // Attempt query to trigger page decryption
        await wrongDb.query('secret_evidence');
        await wrongDb.close();
      } catch (e) {
        wrongKeyFailed = true;
      }
      expect(
        wrongKeyFailed,
        isTrue,
        reason: 'SQLCipher must reject wrong encryption key',
      );

      // 4. Reopen without password -> standard SQLite cannot read SQLCipher encrypted file
      bool plaintextAccessFailed = false;
      try {
        final plainDb = await openDatabase(
          dbPath,
          singleInstance: false,
          version: 1,
        );
        await plainDb.query('secret_evidence');
        await plainDb.close();
      } catch (e) {
        plaintextAccessFailed = true;
      }
      expect(
        plaintextAccessFailed,
        isTrue,
        reason:
            'Encrypted database file cannot be read as ordinary plaintext SQLite',
      );

      // Clean up
      await deleteDatabase(dbPath);
    });
  });
}
