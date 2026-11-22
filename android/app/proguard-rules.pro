# kotlinx.serialization: keep generated serializers of our API models
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class com.opcodelabs.learn.data.** {
    *** Companion;
}
-keepclasseswithmembers class com.opcodelabs.learn.data.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.opcodelabs.learn.data.**$$serializer { *; }
-dontwarn org.slf4j.**
