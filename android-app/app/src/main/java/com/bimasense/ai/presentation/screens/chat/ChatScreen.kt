package com.bimasense.ai.presentation.screens.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bimasense.ai.data.repository.BimaSenseRepository
import com.bimasense.ai.domain.model.ChatMessage
import com.bimasense.ai.domain.model.Citation
import com.bimasense.ai.domain.model.SseStreamEvent
import com.bimasense.ai.domain.usecase.AskPolicyStreamUseCase
import com.bimasense.ai.presentation.components.CitationChip
import com.bimasense.ai.presentation.components.PdfPageBottomSheet
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import java.util.UUID
import javax.inject.Inject

/**
 * Screen 2: Smart Insurance Chat Screen (`ChatScreen.kt` + `ChatViewModel`).
 * Streams real-time tokens via Server-Sent Events (SSE) using OkHttp and renders
 * clickable `[Page X]` CitationChips that open the in-app `PdfRenderer` bottom sheet.
 */

data class ChatUiState(
    val selectedPlan: String? = "Optima Secure",
    val messages: List<ChatMessage> = listOf(
        ChatMessage(
            id = "welcome-msg",
            isUser = false,
            markdownText = "Namaste! I am **BimaSense AI**, your Medical Insurance & IRDAI Copilot. Ask me anything about waiting periods, room rent sub-limits, non-payable consumables, or unfair claim rejections.",
            followUpSuggestions = listOf(
                "What is the waiting period for sugar and BP in HDFC Optima Secure?",
                "Are surgical gloves and patient gown covered in Optima Secure?",
                "Can an insurer reject my claim after 4 years of continuous renewal?"
            )
        )
    ),
    val activeCitationForPdf: Citation? = null,
    val activePdfFile: File? = null
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val askPolicyStreamUseCase: AskPolicyStreamUseCase,
    private val repository: BimaSenseRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    fun setSelectedPlan(plan: String?) {
        _uiState.value = _uiState.value.copy(selectedPlan = plan)
    }

    fun sendQuery(queryText: String) {
        if (queryText.isBlank()) return
        val userMsg = ChatMessage(
            id = UUID.randomUUID().toString(),
            isUser = true,
            markdownText = queryText
        )
        val assistantMsgId = UUID.randomUUID().toString()
        val placeholderAssistant = ChatMessage(
            id = assistantMsgId,
            isUser = false,
            markdownText = "",
            activeNodeStatus = "Connecting to LangGraph Orchestrator...",
            isStreaming = true
        )

        _uiState.value = _uiState.value.copy(
            messages = _uiState.value.messages + userMsg + placeholderAssistant
        )

        viewModelScope.launch {
            var accumulatedText = ""
            askPolicyStreamUseCase(
                query = queryText,
                selectedPlan = _uiState.value.selectedPlan
            ).collect { event ->
                when (event) {
                    is SseStreamEvent.NodeStatus -> {
                        updateAssistantMessage(assistantMsgId) {
                            it.copy(activeNodeStatus = event.step)
                        }
                    }
                    is SseStreamEvent.TokenDelta -> {
                        accumulatedText += event.delta
                        updateAssistantMessage(assistantMsgId) {
                            it.copy(markdownText = accumulatedText)
                        }
                    }
                    is SseStreamEvent.Complete -> {
                        updateAssistantMessage(assistantMsgId) {
                            it.copy(
                                markdownText = event.answerMarkdown,
                                intent = event.intent,
                                citations = event.citations,
                                comparisonTable = event.comparisonTable,
                                followUpSuggestions = event.followUpSuggestions,
                                activeNodeStatus = null,
                                isStreaming = false
                            )
                        }
                    }
                    is SseStreamEvent.Error -> {
                        updateAssistantMessage(assistantMsgId) {
                            it.copy(
                                markdownText = accumulatedText.ifBlank { "Error: ${event.message}" },
                                activeNodeStatus = null,
                                isStreaming = false
                            )
                        }
                    }
                }
            }
        }
    }

    fun openCitationPdf(citation: Citation) {
        viewModelScope.launch {
            val policyId = when {
                citation.sourceTitle.contains("Optima", ignoreCase = true) -> "hdfc-optima-secure"
                citation.sourceTitle.contains("Star", ignoreCase = true) -> "star-comprehensive"
                citation.sourceTitle.contains("ReAssure", ignoreCase = true) -> "niva-bupa-reassure-2"
                else -> "hdfc-optima-secure"
            }
            val pdfFile = repository.getOrDownloadPolicyPdf(policyId, "$policyId.pdf").getOrNull()
            _uiState.value = _uiState.value.copy(
                activeCitationForPdf = citation,
                activePdfFile = pdfFile
            )
        }
    }

    fun dismissCitationSheet() {
        _uiState.value = _uiState.value.copy(activeCitationForPdf = null, activePdfFile = null)
    }

    private fun updateAssistantMessage(msgId: String, transform: (ChatMessage) -> ChatMessage) {
        _uiState.value = _uiState.value.copy(
            messages = _uiState.value.messages.map { msg ->
                if (msg.id == msgId) transform(msg) else msg
            }
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChatScreen(
    viewModel: ChatViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    var inputQuery by remember { mutableStateOf("") }

    val availablePlans = listOf("All Plans", "Optima Secure", "Star Comprehensive", "ReAssure 2.0")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 10.dp)
    ) {
        // Active Plan Filter Strip
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            availablePlans.forEach { plan ->
                val effectiveSelection = state.selectedPlan ?: "All Plans"
                FilterChip(
                    selected = effectiveSelection == plan,
                    onClick = {
                        viewModel.setSelectedPlan(if (plan == "All Plans") null else plan)
                    },
                    label = { Text(plan, style = MaterialTheme.typography.labelMedium) }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Message Stream
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            items(state.messages, key = { it.id }) { msg ->
                ChatMessageBubble(
                    message = msg,
                    onCitationClick = { viewModel.openCitationPdf(it) },
                    onSuggestionClick = { viewModel.sendQuery(it) }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Input Composer
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            OutlinedTextField(
                value = inputQuery,
                onValueChange = { inputQuery = it },
                placeholder = { Text("Ask about waiting periods, room rent, or IRDAI rules...") },
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier.weight(1f)
            )
            Spacer(modifier = Modifier.width(8.dp))
            IconButton(
                onClick = {
                    val q = inputQuery.trim()
                    if (q.isNotEmpty()) {
                        inputQuery = ""
                        viewModel.sendQuery(q)
                    }
                }
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.Send,
                    contentDescription = "Send Query",
                    tint = MaterialTheme.colorScheme.primary
                )
            }
        }
    }

    state.activeCitationForPdf?.let { cit ->
        PdfPageBottomSheet(
            citation = cit,
            pdfFile = state.activePdfFile,
            onDismiss = { viewModel.dismissCitationSheet() }
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChatMessageBubble(
    message: ChatMessage,
    onCitationClick: (Citation) -> Unit,
    onSuggestionClick: (String) -> Unit
) {
    val alignment = if (message.isUser) Alignment.End else Alignment.Start
    Column(
        horizontalAlignment = alignment,
        modifier = Modifier.fillMaxWidth()
    ) {
        message.activeNodeStatus?.let { step ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .padding(bottom = 4.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(MaterialTheme.colorScheme.secondaryContainer)
                    .padding(horizontal = 10.dp, vertical = 4.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.AutoAwesome,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = step,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (message.isUser) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.65f)
                }
            ),
            modifier = Modifier.fillMaxWidth(if (message.isUser) 0.85f else 0.96f)
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(
                    text = message.markdownText.ifBlank { "..." },
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (message.isUser) {
                        MaterialTheme.colorScheme.onPrimary
                    } else {
                        MaterialTheme.colorScheme.onSurface
                    }
                )

                if (message.citations.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = "CLICKABLE PAGE CITATIONS (TAP TO VIEW PDF CLAUSE):",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        message.citations.forEach { citation ->
                            CitationChip(
                                citation = citation,
                                onClick = onCitationClick
                            )
                        }
                    }
                }
            }
        }

        if (!message.isUser && message.followUpSuggestions.isNotEmpty()) {
            Spacer(modifier = Modifier.height(6.dp))
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                message.followUpSuggestions.forEach { suggestion ->
                    SuggestionChip(
                        onClick = { onSuggestionClick(suggestion) },
                        label = {
                            Text(
                                text = suggestion,
                                style = MaterialTheme.typography.labelSmall,
                                color = Color(0xFF1E3A8A)
                            )
                        }
                    )
                }
            }
        }
    }
}
