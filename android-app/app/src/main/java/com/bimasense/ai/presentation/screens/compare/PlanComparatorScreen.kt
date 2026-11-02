package com.bimasense.ai.presentation.screens.compare

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bimasense.ai.domain.model.ComparisonRow
import com.bimasense.ai.domain.usecase.ComparePlansUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Screen 3: Multi-Insurer Side-by-Side Plan Comparator Screen (`PlanComparatorScreen.kt`).
 * Compares Plan A vs. Plan B across Room Rent, Maternity, Restoration, Consumables,
 * Senior Co-Pay, and PED Waiting Period.
 */

data class PlanComparatorUiState(
    val planA: String = "Star Comprehensive",
    val planB: String = "ReAssure 2.0",
    val selectedCriteria: Set<String> = setOf(
        "Room Rent & ICU Limit",
        "PED Waiting Period (Excl01)",
        "Maternity Waiting & Sub-Limit",
        "Restoration Benefit",
        "Non-Payable Consumables (68 Items)",
        "Senior Citizen Co-Payment"
    ),
    val isLoading: Boolean = false,
    val comparisonRows: List<ComparisonRow> = emptyList(),
    val errorMessage: String? = null
)

@HiltViewModel
class PlanComparatorViewModel @Inject constructor(
    private val comparePlansUseCase: ComparePlansUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlanComparatorUiState())
    val uiState: StateFlow<PlanComparatorUiState> = _uiState.asStateFlow()

    init {
        runComparison()
    }

    fun selectPlanA(plan: String) {
        _uiState.value = _uiState.value.copy(planA = plan)
        runComparison()
    }

    fun selectPlanB(plan: String) {
        _uiState.value = _uiState.value.copy(planB = plan)
        runComparison()
    }

    fun toggleCriterion(criterion: String) {
        val current = _uiState.value.selectedCriteria.toMutableSet()
        if (current.contains(criterion) && current.size > 1) {
            current.remove(criterion)
        } else {
            current.add(criterion)
        }
        _uiState.value = _uiState.value.copy(selectedCriteria = current)
    }

    fun runComparison() {
        val current = _uiState.value
        viewModelScope.launch {
            _uiState.value = current.copy(isLoading = true, errorMessage = null)
            comparePlansUseCase(
                planA = current.planA,
                planB = current.planB,
                criteria = current.selectedCriteria.toList()
            ).onSuccess { (_, rows) ->
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    comparisonRows = rows
                )
            }.onFailure { err ->
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    errorMessage = err.localizedMessage
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PlanComparatorScreen(
    viewModel: PlanComparatorViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val plans = listOf("Optima Secure", "Star Comprehensive", "ReAssure 2.0")
    val allCriteria = listOf(
        "Room Rent & ICU Limit",
        "PED Waiting Period (Excl01)",
        "Maternity Waiting & Sub-Limit",
        "Restoration Benefit",
        "Non-Payable Consumables (68 Items)",
        "Senior Citizen Co-Payment"
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text(
            text = "Multi-Insurer Plan Comparator",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Side-by-side clause comparison backed by policy wordings",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Plan A Selector
        Text("Plan A:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            plans.forEach { p ->
                FilterChip(
                    selected = state.planA == p,
                    onClick = { viewModel.selectPlanA(p) },
                    label = { Text(p) }
                )
            }
        }

        // Plan B Selector
        Text("Plan B:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            plans.forEach { p ->
                FilterChip(
                    selected = state.planB == p,
                    onClick = { viewModel.selectPlanB(p) },
                    label = { Text(p) }
                )
            }
        }

        Spacer(modifier = Modifier.height(6.dp))

        // Criteria Chips
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            allCriteria.forEach { crit ->
                FilterChip(
                    selected = state.selectedCriteria.contains(crit),
                    onClick = { viewModel.toggleCriterion(crit) },
                    label = { Text(crit, style = MaterialTheme.typography.labelSmall) }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Button(
            onClick = { viewModel.runComparison() },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Compare ${state.planA} vs. ${state.planB}")
        }

        Spacer(modifier = Modifier.height(12.dp))

        if (state.isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize()
            ) {
                items(state.comparisonRows, key = { it.criterion }) { row ->
                    ComparisonMatrixCard(row)
                }
            }
        }
    }
}

@Composable
private fun ComparisonMatrixCard(row: ComparisonRow) {
    Card(
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
        ),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(
                text = row.criterion,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = row.planAValue,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = row.planBValue,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
            if (row.verdict.isNotBlank()) {
                Spacer(modifier = Modifier.height(8.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(6.dp))
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xFFDBEAFE))
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = "Verdict: ${row.verdict}",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF1E3A8A)
                    )
                }
            }
        }
    }
}
