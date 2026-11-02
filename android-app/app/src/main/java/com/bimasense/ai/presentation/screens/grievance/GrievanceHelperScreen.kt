package com.bimasense.ai.presentation.screens.grievance

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import com.bimasense.ai.domain.model.GrievanceAuditResult
import com.bimasense.ai.domain.usecase.VerifyGrievanceUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Screen 5: Claim Rejection & IRDAI Helper Screen (`GrievanceHelperScreen.kt`).
 * Step-by-step wizard verifying IRDAI Master Circular 2024 rules (36-month moratorium,
 * 3-hour cashless discharge limit, TPA direct rejection ban) and generating a ready-to-send
 * Grievance Redressal Officer (GRO) escalation email.
 */

data class GrievanceUiState(
    val insurerName: String = "Star Health",
    val planName: String = "Star Comprehensive",
    val continuousPolicyMonths: Float = 42f,
    val rejectionReason: String = "Rejected citing non-disclosure of pre-existing hypertension",
    val dischargeWaitHours: Float = 6.5f,
    val rejectedByTpaDirectly: Boolean = true,
    val ombudsmanOverdueDays: Int = 5,
    val isLoading: Boolean = false,
    val auditResult: GrievanceAuditResult? = null
)

@HiltViewModel
class GrievanceViewModel @Inject constructor(
    private val verifyGrievanceUseCase: VerifyGrievanceUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(GrievanceUiState())
    val uiState: StateFlow<GrievanceUiState> = _uiState.asStateFlow()

    init {
        runAudit()
    }

    fun updateState(transform: (GrievanceUiState) -> GrievanceUiState) {
        _uiState.value = transform(_uiState.value)
    }

    fun runAudit() {
        val s = _uiState.value
        viewModelScope.launch {
            _uiState.value = s.copy(isLoading = true)
            verifyGrievanceUseCase(
                insurerName = s.insurerName,
                planName = s.planName,
                continuousMonths = s.continuousPolicyMonths.toInt(),
                rejectionReason = s.rejectionReason,
                dischargeWaitHours = s.dischargeWaitHours.toDouble(),
                rejectedByTpaDirectly = s.rejectedByTpaDirectly,
                ombudsmanOverdueDays = s.ombudsmanOverdueDays
            ).onSuccess { res ->
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    auditResult = res
                )
            }.onFailure {
                _uiState.value = _uiState.value.copy(isLoading = false)
            }
        }
    }
}

@Composable
fun GrievanceHelperScreen(
    viewModel: GrievanceViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val scrollState = rememberScrollState()
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = Icons.Default.Gavel,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary
            )
            Spacer(modifier = Modifier.padding(4.dp))
            Column {
                Text(
                    text = "IRDAI Rights & Claim Rejection Helper",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Audits rejections against IRDAI Master Circular 2024 (Ref: 84/05/2024)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        OutlinedTextField(
            value = state.insurerName,
            onValueChange = { v -> viewModel.updateState { it.copy(insurerName = v) } },
            label = { Text("Insurer Name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = state.rejectionReason,
            onValueChange = { v -> viewModel.updateState { it.copy(rejectionReason = v) } },
            label = { Text("Insurer's Stated Rejection / Deduction Reason") },
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(10.dp))

        Text(
            text = "Continuous Policy Tenure: ${state.continuousPolicyMonths.toInt()} Months (36M Moratorium Threshold)",
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold
        )
        Slider(
            value = state.continuousPolicyMonths,
            onValueChange = { v -> viewModel.updateState { it.copy(continuousPolicyMonths = v) } },
            valueRange = 1f..96f
        )

        Text(
            text = "Final Cashless Discharge Wait Time: ${"%.1f".format(state.dischargeWaitHours)} Hours (3H IRDAI Limit)",
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold
        )
        Slider(
            value = state.dischargeWaitHours,
            onValueChange = { v -> viewModel.updateState { it.copy(dischargeWaitHours = v) } },
            valueRange = 0.5f..12f
        )

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                text = "Rejected Directly by TPA (No Insurer CRC Approval)",
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium
            )
            Switch(
                checked = state.rejectedByTpaDirectly,
                onCheckedChange = { c -> viewModel.updateState { it.copy(rejectedByTpaDirectly = c) } }
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        Button(
            onClick = { viewModel.runAudit() },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Verify IRDAI Compliance & Draft GRO Notice")
        }

        Spacer(modifier = Modifier.height(14.dp))

        state.auditResult?.let { result ->
            Card(
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(
                    containerColor = if (result.isIllegal) Color(0xFFFEF2F2) else Color(0xFFF0FDF4)
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = if (result.isIllegal) {
                            "IRDAI VIOLATIONS DETECTED (${result.violations.size})"
                        } else {
                            "NO STATUTORY BREACH DETECTED"
                        },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = if (result.isIllegal) Color(0xFFB91C1C) else Color(0xFF15803D)
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    result.violations.forEach { v ->
                        Column(
                            modifier = Modifier
                                .padding(vertical = 4.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(Color.White)
                                .padding(10.dp)
                        ) {
                            Text(
                                text = "${v.clause} (${v.circularRef})",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF991B1B)
                            )
                            Text(
                                text = v.finding,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = "READY-TO-SEND GRO ESCALATION NOTICE:",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = result.groEmailDraft,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier
                            .clip(RoundedCornerShape(10.dp))
                            .background(Color.White)
                            .padding(12.dp)
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedButton(
                        onClick = {
                            val sendIntent = Intent(Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(
                                    Intent.EXTRA_SUBJECT,
                                    "Formal Representation Under IRDAI Circular ${result.circularRef}"
                                )
                                putExtra(Intent.EXTRA_TEXT, result.groEmailDraft)
                            }
                            context.startActivity(Intent.createChooser(sendIntent, "Send GRO Notice via Email"))
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(Icons.Default.Share, contentDescription = null)
                        Spacer(modifier = Modifier.padding(4.dp))
                        Text("Share / Send to Insurer GRO")
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))
    }
}
