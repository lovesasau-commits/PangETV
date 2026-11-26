plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.sasau.pangetv"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.sasau.pangetv"
        minSdk = 21
        targetSdk = 34
        versionCode = 2
        versionName = "1.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // 侧载安装用：先用 debug 签名，保证装得上；正式上架请换成自己的签名
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
        // freeCompilerArgs 是只读 List，必须用赋值而不是 .add()
        freeCompilerArgs = freeCompilerArgs + "-opt-in=androidx.media3.common.util.UnstableApi"
    }

    buildFeatures {
        viewBinding = true
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("com.google.android.material:material:1.12.0")

    implementation("androidx.media3:media3-exoplayer:1.4.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.4.1")
    implementation("androidx.media3:media3-ui:1.4.1")
    // HTTP 层走 OkHttp：Media3 1.4.1 的 DataSource 没有 Dns 抽象，
    // 咪咕 CDN 的 DNS 别名必须靠 OkHttp 的 Dns 钩子实现。
    implementation("androidx.media3:media3-datasource-okhttp:1.4.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
