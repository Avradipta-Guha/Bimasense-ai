package com.bimasense.ai.data.remote

import com.bimasense.ai.BuildConfig
import com.bimasense.ai.domain.model.Citation
import com.bimasense.ai.domain.model.ComparisonRow
import com.bimasense.ai.domain.model.SseStreamEvent
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import javax.inject.Inject
import javax.inject.Singleton

/**
 * OkHttp Server-Sent Events (SSE) Streaming Client (`POST /api/v1/chat/stream`).
 * Connects to FastAPI's SSE endpoint and converts `node_status`, `token`, and `complete`
 * frames into a cold Kotlin `Flow<SseStreamEvent>` for Jetpack Compose state collection.
 */
@Singleton
class SseChatClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val gson: Gson
) {

    fun streamChat(
        query: String,
        selectedPlan: String?,
        userId: String = "global"
    ): Flow<SseStreamEvent> = callbackFlow {
        val requestDto = ChatRequestDto(
            query = query,
            userId = userId,
            selectedPlan = selectedPlan
        )
        val jsonBody = gson.toJson(requestDto)
            .toRequestBody("application/json; charset=utf-8".toMediaType())

        val request = Request.Builder()
            .url("${BuildConfig.BASE_API_URL}api/v1/chat/stream")
            .post(jsonBody)
            .header("Accept", "text/event-stream")
            .build()

        val listener = object : EventSourceListener() {
            override fun onEvent(
                eventSource: EventSource,
                id: String?,
                type: String?,
                data: String
            ) {
                try {
                    when (type) {
                        "node_status" -> {
                            val obj = gson.fromJson(data, JsonObject::class.java)
                            val step = obj.get("step")?.asString ?: "Processing..."
                            trySend(SseStreamEvent.NodeStatus(step))
                        }
                        "token" -> {
                            val obj = gson.fromJson(data, JsonObject::class.java)
                            val delta = obj.get("delta")?.asString ?: ""
                            trySend(SseStreamEvent.TokenDelta(delta))
                        }
                        "complete" -> {
                            val dto = gson.fromJson(data, ChatResponseDto::class.java)
                            val citations = dto.citations.map { c ->
                                Citation(
                                    sourceTitle = c.sourceTitle,
                                    pageNumber = c.pageNumber,
                                    sectionHeading = c.sectionHeading,
                                    sectionCategory = c.sectionCategory,
                                    snippet = c.snippet,
                                    relevanceScore = c.relevanceScore
                                )
                            }
                            val table = dto.comparisonTable?.map { row ->
                                ComparisonRow(
                                    criterion = row.criterion,
                                    planAValue = row.planAValue,
                                    planBValue = row.planBValue,
                                    verdict = row.winnerOrVerdict
                                )
                            } ?: emptyList()

                            trySend(
                                SseStreamEvent.Complete(
                                    intent = dto.intent,
                                    answerMarkdown = dto.answerMarkdown,
                                    citations = citations,
                                    comparisonTable = table,
                                    followUpSuggestions = dto.followUpSuggestions,
                                    confidenceScore = dto.confidenceScore
                                )
                            )
                            channel.close()
                        }
                    }
                } catch (e: Exception) {
                    trySend(SseStreamEvent.Error("Failed to parse SSE frame: ${e.localizedMessage}"))
                }
            }

            override fun onFailure(
                eventSource: EventSource,
                t: Throwable?,
                response: Response?
            ) {
                val msg = t?.localizedMessage ?: "SSE connection failed (HTTP ${response?.code})"
                trySend(SseStreamEvent.Error(msg))
                channel.close()
            }
        }

        val eventSource = EventSources.createFactory(okHttpClient)
            .newEventSource(request, listener)

        awaitClose {
            eventSource.cancel()
        }
    }
}
