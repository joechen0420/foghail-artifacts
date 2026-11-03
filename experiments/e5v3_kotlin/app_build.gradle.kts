plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.foghail.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.foghail.client"
        minSdk = 26
        targetSdk = 36
        versionCode = 5
        versionName = "v6-e3-20261103"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

dependencies {
    implementation("org.bouncycastle:bcprov-jdk18on:1.79")
    testImplementation(libs.junit)
}
