package com.bimasense.ai.di

import android.content.Context
import androidx.room.Room
import com.bimasense.ai.BuildConfig
import com.bimasense.ai.data.local.BimaSenseDatabase
import com.bimasense.ai.data.local.ChatHistoryDao
import com.bimasense.ai.data.local.PolicyDao
import com.bimasense.ai.data.remote.BimaSenseApiService
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

/**
 * Hilt Dependency Injection Module (`NetworkModule` + `DatabaseModule`) for BimaSense AI.
 */
@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideGson(): Gson = GsonBuilder().setLenient().create()

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        return OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, gson: Gson): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_API_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()

    @Provides
    @Singleton
    fun provideBimaSenseApiService(retrofit: Retrofit): BimaSenseApiService =
        retrofit.create(BimaSenseApiService::class.java)

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): BimaSenseDatabase =
        Room.databaseBuilder(
            context,
            BimaSenseDatabase::class.java,
            "bimasense_ai.db"
        ).fallbackToDestructiveMigration().build()

    @Provides
    fun providePolicyDao(db: BimaSenseDatabase): PolicyDao = db.policyDao()

    @Provides
    fun provideChatHistoryDao(db: BimaSenseDatabase): ChatHistoryDao = db.chatHistoryDao()
}
