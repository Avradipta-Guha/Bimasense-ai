package com.bimasense.ai.data.local

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/**
 * Room Local Database Entities, DAOs, and Database class for offline caching
 * of Insurance Policies and Chat History (Milestone 5).
 */

@Entity(tableName = "cached_policies")
data class PolicyEntity(
    @PrimaryKey val policyId: String,
    val insurerName: String,
    val planName: String,
    val uin: String,
    val sumInsuredOptionsCsv: String,
    val roomRentRule: String,
    val pedWaitingPeriod: String,
    val restorationRule: String,
    val consumablesCoverage: String,
    val coPaymentRule: String,
    val isUserUploaded: Boolean,
    val fileName: String,
    val totalPages: Int,
    val localPdfPath: String? = null
)

@Entity(tableName = "chat_history")
data class ChatMessageEntity(
    @PrimaryKey val id: String,
    val timestampMs: Long,
    val isUser: Boolean,
    val markdownText: String,
    val intent: String,
    val citationsJson: String,
    val selectedPlan: String?
)

@Dao
interface PolicyDao {
    @Query("SELECT * FROM cached_policies ORDER BY isUserUploaded DESC, insurerName ASC")
    fun observePolicies(): Flow<List<PolicyEntity>>

    @Query("SELECT * FROM cached_policies")
    suspend fun getAllPolicies(): List<PolicyEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPolicies(policies: List<PolicyEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPolicy(policy: PolicyEntity)
}

@Dao
interface ChatHistoryDao {
    @Query("SELECT * FROM chat_history ORDER BY timestampMs ASC")
    fun observeChatHistory(): Flow<List<ChatMessageEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertMessage(message: ChatMessageEntity)

    @Query("DELETE FROM chat_history")
    suspend fun clearHistory()
}

@Database(
    entities = [PolicyEntity::class, ChatMessageEntity::class],
    version = 1,
    exportSchema = false
)
abstract class BimaSenseDatabase : RoomDatabase() {
    abstract fun policyDao(): PolicyDao
    abstract fun chatHistoryDao(): ChatHistoryDao
}
