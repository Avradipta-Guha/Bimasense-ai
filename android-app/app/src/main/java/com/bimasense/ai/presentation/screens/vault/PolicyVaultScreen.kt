package com.bimasense.ai.presentation.screens.vault

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bimasense.ai.domain.model.PolicySummary
import com.bimasense.ai.domain.usecase.GetPoliciesUseCase
import com.bimasense.ai.domain.usecase.UploadPolicyPdfUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * Screen 1: Home & Policy Vault Screen (`PolicyVaultScreen.kt` + `PolicyVaultViewModel`).
 * Displays pre-loaded Indian health insurance plans + user-uploaded PDFs using
 * `ActivityResultContracts.OpenDocument`.
 */

data class PolicyVaultUiState(
    val isLoading: Boolean = false,
    val policies: List<PolicySummary> = emptyList(),
    val activePlanName: String = "Optima Secure",
    val uploadStatusMessage: String? = null,
    val errorMessage: String? = null
)

@HiltViewModel
class PolicyVaultViewModel @Inject constructor(
    private val getPoliciesUseCase: GetPoliciesUseCase,
    private val uploadPolicyPdfUseCase: UploadPolicyPdfUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(PolicyVaultUiState(isLoading = true))
    val uiState: StateFlow<PolicyVaultUiState> = _uiState.asStateFlow()

    init {
        loadPolicies()
    }

    fun loadPolicies(userId: String = "android_user_01") {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = null)
            getPoliciesUseCase(userId)
                .onSuccess { list ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        policies = list
                    )
                }
                .onFailure { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Failed to load policies"
                    )
                }
        }
    }

    fun selectActivePlan(planName: String) {
        _uiState.value = _uiState.value.copy(activePlanName = planName)
    }

    fun uploadUserPdf(
        context: Context,
        uri: Uri,
        insurerName: String,
        planName: String,
        userId: String = "android_user_01"
    ) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoading = true,
                uploadStatusMessage = "Parsing PDF tables & indexing into Qdrant..."
            )
            try {
                val tempFile = File(context.cacheDir, "${planName.replace(" ", "_")}.pdf")
                context.contentResolver.openInputStream(uri)?.use { input ->
                    tempFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
                uploadPolicyPdfUseCase(tempFile, insurerName, planName, userId)
                    .onSuccess { uploaded ->
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            activePlanName = uploaded.planName,
                            uploadStatusMessage = "Indexed ${uploaded.planName} (${uploaded.totalPages} pages)"
                        )
                        loadPolicies(userId)
                    }
                    .onFailure { err ->
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            errorMessage = "Upload failed: ${err.localizedMessage}"
                        )
                    }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    errorMessage = "Could not read selected PDF: ${e.localizedMessage}"
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PolicyVaultScreen(
    onOpenChatWithPlan: (String) -> Unit,
    viewModel: PolicyVaultViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    var pendingPdfUri by remember { mutableStateOf<Uri?>(null) }
    var customInsurer by remember { mutableStateOf("HDFC ERGO") }
    var customPlan by remember { mutableStateOf("My Personal Health Policy") }

    val openDocumentLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) {
            pendingPdfUri = uri
        }
    }

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { openDocumentLauncher.launch(arrayOf("application/pdf")) },
                icon = { Icon(Icons.Default.CloudUpload, contentDescription = "Upload Policy PDF") },
                text = { Text("Upload Policy PDF") },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(
                    imageVector = Icons.Default.Shield,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(30.dp)
                )
                Spacer(modifier = Modifier.width(10.dp))
                Column {
                    Text(
                        text = "BimaSense AI Policy Vault",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Select an active policy or upload your Policy Wording PDF",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            state.uploadStatusMessage?.let { msg ->
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = msg,
                    style = MaterialTheme.typography.labelMedium,
                    color = Color(0xFF15803D),
                    fontWeight = FontWeight.SemiBold
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (state.isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(state.policies, key = { it.policyId }) { policy ->
                        val isSelected = policy.planName == state.activePlanName
                        PolicySummaryCardItem(
                            policy = policy,
                            isSelected = isSelected,
                            onSelect = {
                                viewModel.selectActivePlan(policy.planName)
                                onOpenChatWithPlan(policy.planName)
                            }
                        )
                    }
                    item { Spacer(modifier = Modifier.height(72.dp)) }
                }
            }
        }
    }

    if (pendingPdfUri != null) {
        AlertDialog(
            onDismissRequest = { pendingPdfUri = null },
            title = { Text("Index Personal Policy PDF") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = customInsurer,
                        onValueChange = { customInsurer = it },
                        label = { Text("Insurer Name") },
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = customPlan,
                        onValueChange = { customPlan = it },
                        label = { Text("Plan / Policy Schedule Name") },
                        singleLine = true
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        pendingPdfUri?.let { uri ->
                            viewModel.uploadUserPdf(context, uri, customInsurer, customPlan)
                        }
                        pendingPdfUri = null
                    }
                ) {
                    Text("Parse & Index")
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingPdfUri = null }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PolicySummaryCardItem(
    policy: PolicySummary,
    isSelected: Boolean,
    onSelect: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isSelected) {
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)
            } else {
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
            }
        ),
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onSelect() }
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.HealthAndSafety,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Column {
                        Text(
                            text = "${policy.insurerName} — ${policy.planName}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "UIN: ${policy.uin} • ${policy.totalPages} Pages",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                if (isSelected) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Active Plan",
                        tint = Color(0xFF15803D)
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                policy.sumInsuredOptions.forEach { si ->
                    SuggestionChip(
                        onClick = onSelect,
                        label = { Text("SI: $si", style = MaterialTheme.typography.labelSmall) }
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            PolicyClauseRow("Room Rent Rule", policy.roomRentRule)
            PolicyClauseRow("PED Waiting Period", policy.pedWaitingPeriod)
            PolicyClauseRow("Restoration Benefit", policy.restorationRule)
            PolicyClauseRow("68 Consumables Cover", policy.consumablesCoverage)
            PolicyClauseRow("Senior Co-Payment", policy.coPaymentRule)
        }
    }
}

@Composable
private fun PolicyClauseRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = "$label:",
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(0.42f)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(0.58f)
        )
    }
}
