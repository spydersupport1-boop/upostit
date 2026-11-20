# ==============================================================================
# UPOSTIT Mobile — Production ProGuard & R8 Optimization Rules
# ==============================================================================

# 1. SQLCipher Native Encryption & Database Engine Preservation
-keep class net.sqlcipher.** { *; }
-keep interface net.sqlcipher.** { *; }
-keep class net.sqlcipher.database.** { *; }
-keepclassmembers class net.sqlcipher.database.** { *; }
-dontwarn net.sqlcipher.**

# 2. Flutter Secure Storage & Android Keystore Integration
-keep class androidx.security.crypto.** { *; }
-keep class com.it_nomads.fluttersecurestorage.** { *; }
-dontwarn androidx.security.crypto.**

# 3. Android Support & Architecture Components
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod

# 4. Gson / Jackson / JSON Serialization Preservation
-keepclassmembers enum * { *; }
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    !static !transient <fields>;
    !private <fields>;
    !private <methods>;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}

