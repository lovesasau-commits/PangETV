# Media3 / ExoPlayer
-dontwarn androidx.media3.**
-keep class androidx.media3.** { *; }

# 保留应用自己的数据类（通过 Intent 传参）
-keep class com.sasau.pangetv.model.** { *; }
