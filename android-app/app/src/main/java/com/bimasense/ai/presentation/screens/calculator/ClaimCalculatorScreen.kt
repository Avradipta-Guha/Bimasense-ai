package com.bimasense.ai.presentation.screens.calculator

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bimasense.ai.domain.model.ClaimEstimateInput
import com.bimasense.ai.domain.model.ClaimEstimateResult
import com.bimasense.ai.domain.usecase.CalculateClaimUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Screen 4: Claim & Deductible Estimator Screen (`ClaimCalculatorScreen.kt`).
 * Interactive sliders for Room Rent Cap, Actual Room Rent, Total Bill, Exempt Medicines/Stents,
 * Consumables, and Senior Co-Pay, with a custom Jetpack Compose `Canvas` Donut Chart.
 */

data class ClaimCalculatorUiState(
    val planName: String = "Star Comprehensive",
    val sumInsured: Float = 1_000_000f,
    val totalBill: Float = 150_000f,
    val allowedRoomRent: Float = 5_000f,
    val actualRoomRent: Float = 10_000f,
    val exemptMedicinesAndStents: Float = 30_000f,
    val consumablesAmount: Float = 10_000f,
    val hasConsumablesRider: Boolean = false,
    val deductible: Float = 0f,
    val coPayPercent: Float = 10f,
    val result: ClaimEstimateResult? = null,
    val isLoading: Boolean = false
)

@HiltViewModel
class ClaimCalculatorViewModel @Inject constructor(
    private val calculateClaimUseCase: CalculateClaimUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(ClaimCalculatorUiState())
    val uiState: StateFlow<ClaimCalculatorUiState> = _uiState.asStateFlow()

    init {
        recalculate()
    }

    fun updateParameters(transform: (ClaimCalculatorUiState) -> ClaimCalculatorUiState) {
        _uiState.value = transform(_uiState.value)
        recalculate()
    }

    fun recalculate() {
        val s = _uiState.value
        val associated = (s.totalBill - s.exemptMedicinesAndStents - s.consumablesAmount).coerceAtLeast(0f)

        // Instant local deterministic preview + remote FastAPI rule verification
        val ratio = if (s.allowedRoomRent > 0f && s.actualRoomRent > s.allowedRoomRent) {
            (s.allowedRoomRent / s.actualRoomRent).toDouble()
        } else {
            1.0
        }
        val payableSubject = associated.toDouble() * ratio
        val propDeduction = associated.toDouble() - payableSubject
        val consumableDed = if (s.hasConsumablesRider) 0.0 else s.consumablesAmount.toDouble()
        val payableConsumable = if (s.hasConsumablesRider) s.consumablesAmount.toDouble() else 0.0
        val grossAdmissible = payableSubject + s.exemptMedicinesAndStents.toDouble() + payableConsumable
        val appliedDed = s.deductible.toDouble().coerceAtMost(grossAdmissible)
        val afterDed = (grossAdmissible - appliedDed).coerceAtLeast(0.0)
        val copayDed = afterDed * (s.coPayPercent.toDouble() / 100.0)
        val finalPayable = (afterDed - copayDed).coerceAtMost(s.sumInsured.toDouble())
        val outOfPocket = (s.totalBill.toDouble() - finalPayable).coerceAtLeast(0.0)

        val localPreview = ClaimEstimateResult(
            planName = s.planName,
            sumInsured = s.sumInsured.toDouble(),
            totalHospitalBill = s.totalBill.toDouble(),
            proportionateMultiplier = ratio,
            proportionateDeductionAmount = propDeduction,
            nonPayableConsumablesDeduction = consumableDed,
            deductibleApplied = appliedDed,
            coPaymentPercentage = s.coPayPercent.toDouble(),
            coPaymentDeductionAmount = copayDed,
            finalPayableClaimAmount = finalPayable,
            totalOutOfPocketCost = outOfPocket,
            itemizedNotes = listOf(
                "Room Rent Proportionate Factor: ${(ratio * 100).toInt()}%",
                "Exempt Medicines/Stents/ICU (Rs. ${s.exemptMedicinesAndStents.toInt()}) paid at 100% without proportionate deduction."
            ),
            citations = emptyList()
        )
        _uiState.value = s.copy(result = localPreview)

        viewModelScope.launch {
            val input = ClaimEstimateInput(
                planName = s.planName,
                sumInsured = s.sumInsured.toDouble(),
                totalBill = s.totalBill.toDouble(),
                allowedRoomRent = s.allowedRoomRent.toDouble(),
                actualRoomRent = s.actualRoomRent.toDouble(),
                associatedMedicalExpenses = associated.toDouble(),
                exemptExpensesMedicinesImplantsIcu = s.exemptMedicinesAndStents.toDouble(),
                consumablesAmount = s.consumablesAmount.toDouble(),
                hasConsumablesRider = s.hasConsumablesRider,
                deductible = s.deductible.toDouble(),
                coPayPercent = s.coPayPercent.toDouble()
            )
            calculateClaimUseCase(input).onSuccess { remoteResult ->
                _uiState.value = _uiState.value.copy(result = remoteResult)
            }
        }
    }
}

@Composable
fun ClaimCalculatorScreen(
    viewModel: ClaimCalculatorViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val scrollState = rememberScrollState()
    val plans = listOf("Optima Secure", "Star Comprehensive", "ReAssure 2.0")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(16.dp)
    ) {
        Text(
            text = "Deterministic Claim & Room-Rent Calculator",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Exact proportionate deduction, exempt items & consumable math",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(modifier = Modifier.height(10.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            plans.forEach { p ->
                FilterChip(
                    selected = state.planName == p,
                    onClick = {
                        viewModel.updateParameters {
                            it.copy(
                                planName = p,
                                hasConsumablesRider = (p == "Optima Secure"),
                                allowedRoomRent = if (p == "Optima Secure" || p == "ReAssure 2.0") it.actualRoomRent else 5000f
                            )
                        }
                    },
                    label = { Text(p, style = MaterialTheme.typography.labelSmall) }
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Compose Canvas Donut Payout Chart Card
        state.result?.let { res ->
            ClaimDonutChartCard(result = res)
        }

        Spacer(modifier = Modifier.height(14.dp))

        SliderInputItem(
            label = "Total Hospital Bill",
            value = state.totalBill,
            range = 25_000f..1_000_000f,
            step = 5_000f,
            onValueChange = { v -> viewModel.updateParameters { it.copy(totalBill = v) } }
        )

        SliderInputItem(
            label = "Allowed Room Rent Cap / Day",
            value = state.allowedRoomRent,
            range = 2_000f..25_000f,
            step = 1_000f,
            onValueChange = { v -> viewModel.updateParameters { it.copy(allowedRoomRent = v) } }
        )

        SliderInputItem(
            label = "Actual Room Rent Chosen / Day",
            value = state.actualRoomRent,
            range = 2_000f..25_000f,
            step = 1_000f,
            onValueChange = { v -> viewModel.updateParameters { it.copy(actualRoomRent = v) } }
        )

        SliderInputItem(
            label = "Exempt Items (Medicines / Stents / ICU)",
            value = state.exemptMedicinesAndStents,
            range = 0f..300_000f,
            step = 5_000f,
            onValueChange = { v -> viewModel.updateParameters { it.copy(exemptMedicinesAndStents = v) } }
        )

        SliderInputItem(
            label = "Billed Consumables (68 Annexure-I Items)",
            value = state.consumablesAmount,
            range = 0f..100_000f,
            step = 2_000f,
            onValueChange = { v -> viewModel.updateParameters { it.copy(consumablesAmount = v) } }
        )

        SliderInputItem(
            label = "Mandatory Co-Payment (%)",
            value = state.coPayPercent,
            range = 0f..30f,
            step = 5f,
            isPercentage = true,
            onValueChange = { v -> viewModel.updateParameters { it.copy(coPayPercent = v) } }
        )

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp)
        ) {
            Text(
                text = "Active Consumables Rider (Protect / Safeguard+)",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Switch(
                checked = state.hasConsumablesRider,
                onCheckedChange = { checked ->
                    viewModel.updateParameters { it.copy(hasConsumablesRider = checked) }
                }
            )
        }

        Button(
            onClick = { viewModel.recalculate() },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Verify Calculation with FastAPI Backend")
        }

        Spacer(modifier = Modifier.height(24.dp))
    }
}

@Composable
private fun ClaimDonutChartCard(result: ClaimEstimateResult) {
    val total = result.totalHospitalBill.coerceAtLeast(1.0).toFloat()
    val payableSweep = ((result.finalPayableClaimAmount.toFloat() / total) * 360f).coerceIn(0f, 360f)
    val propDedSweep = ((result.proportionateDeductionAmount.toFloat() / total) * 360f).coerceIn(0f, 360f)
    val consSweep = ((result.nonPayableConsumablesDeduction.toFloat() / total) * 360f).coerceIn(0f, 360f)
    val copaySweep = (360f - payableSweep - propDedSweep - consSweep).coerceAtLeast(0f)

    val colorPayable = Color(0xFF16A34A)
    val colorPropDed = Color(0xFFDC2626)
    val colorConsDed = Color(0xFFF59E0B)
    val colorCopay = Color(0xFF6366F1)

    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
        ),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()
            ) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier.size(130.dp)
                ) {
                    Canvas(modifier = Modifier.size(110.dp)) {
                        val strokeWidth = 24f
                        val arcSize = Size(size.width, size.height)
                        var startAngle = -90f

                        drawArc(
                            color = colorPayable,
                            startAngle = startAngle,
                            sweepAngle = payableSweep,
                            useCenter = false,
                            size = arcSize,
                            style = Stroke(width = strokeWidth, cap = StrokeCap.Butt)
                        )
                        startAngle += payableSweep

                        drawArc(
                            color = colorPropDed,
                            startAngle = startAngle,
                            sweepAngle = propDedSweep,
                            useCenter = false,
                            size = arcSize,
                            style = Stroke(width = strokeWidth, cap = StrokeCap.Butt)
                        )
                        startAngle += propDedSweep

                        drawArc(
                            color = colorConsDed,
                            startAngle = startAngle,
                            sweepAngle = consSweep,
                            useCenter = false,
                            size = arcSize,
                            style = Stroke(width = strokeWidth, cap = StrokeCap.Butt)
                        )
                        startAngle += consSweep

                        if (copaySweep > 0f) {
                            drawArc(
                                color = colorCopay,
                                startAngle = startAngle,
                                sweepAngle = copaySweep,
                                useCenter = false,
                                size = arcSize,
                                style = Stroke(width = strokeWidth, cap = StrokeCap.Butt)
                            )
                        }
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "${((result.finalPayableClaimAmount / result.totalHospitalBill.coerceAtLeast(1.0)) * 100).toInt()}%",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = colorPayable
                        )
                        Text(
                            text = "Covered",
                            style = MaterialTheme.typography.labelSmall
                        )
                    }
                }

                Spacer(modifier = Modifier.width(16.dp))

                Column(
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    LegendRow(colorPayable, "Insurer Payable", result.finalPayableClaimAmount)
                    LegendRow(colorPropDed, "Room Proportionate Loss", result.proportionateDeductionAmount)
                    LegendRow(colorConsDed, "Consumables Deduction", result.nonPayableConsumablesDeduction)
                    LegendRow(colorCopay, "Co-Pay / Deductible", result.coPaymentDeductionAmount + result.deductibleApplied)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            result.itemizedNotes.forEach { note ->
                Text(
                    text = "• $note",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun LegendRow(color: Color, label: String, amount: Double) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .clip(CircleShape)
                    .background(color)
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(text = label, style = MaterialTheme.typography.labelSmall)
        }
        Text(
            text = "Rs. ${amount.toInt()}",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun SliderInputItem(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    step: Float,
    isPercentage: Boolean = false,
    onValueChange: (Float) -> Unit
) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(
            horizontalArrangement = Arrangement.SpaceBetween,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(text = label, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
            Text(
                text = if (isPercentage) "${value.toInt()}%" else "Rs. ${value.toInt()}",
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
        }
        val stepsCount = ((range.endInclusive - range.start) / step).toInt().coerceAtLeast(1) - 1
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = range,
            steps = stepsCount
        )
    }
}
