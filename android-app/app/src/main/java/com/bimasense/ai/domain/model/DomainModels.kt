package com.bimasense.ai.domain.model

/**
 * Clean Architecture Domain Models for BimaSense AI (Milestone 5).
 * Decoupled from Retrofit DTOs and Room Entities.
 */

data class PolicySummary(
    val policyId: String,
    val insurerName: String,
    val planName: String,
    val uin: String,
    val sumInsuredOptions: List<String>,
    val roomRentRule: String,
    val pedWaitingPeriod: String,
    val restorationRule: String,
    val consumablesCoverage: String,
    val coPaymentRule: String,
    val isUserUploaded: Boolean,
    val fileName: String,
    val totalPages: Int
)

data class Citation(
    val sourceTitle: String,
    val pageNumber: Int,
    val sectionHeading: String,
    val sectionCategory: String,
    val snippet: String,
    val relevanceScore: Float
)

data class ComparisonRow(
    val criterion: String,
    val planAValue: String,
    val planBValue: String,
    val verdict: String
)

data class ChatMessage(
    val id: String,
    val isUser: Boolean,
    val markdownText: String,
    val intent: String = "policy_qa",
    val citations: List<Citation> = emptyList(),
    val comparisonTable: List<ComparisonRow> = emptyList(),
    val followUpSuggestions: List<String> = emptyList(),
    val activeNodeStatus: String? = null,
    val isStreaming: Boolean = false
)

sealed interface SseStreamEvent {
    data class NodeStatus(val step: String) : SseStreamEvent
    data class TokenDelta(val delta: String) : SseStreamEvent
    data class Complete(
        val intent: String,
        val answerMarkdown: String,
        val citations: List<Citation>,
        val comparisonTable: List<ComparisonRow>,
        val followUpSuggestions: List<String>,
        val confidenceScore: Float
    ) : SseStreamEvent
    data class Error(val message: String) : SseStreamEvent
}

data class ClaimEstimateInput(
    val planName: String,
    val sumInsured: Double,
    val totalBill: Double,
    val allowedRoomRent: Double?,
    val actualRoomRent: Double?,
    val associatedMedicalExpenses: Double?,
    val exemptExpensesMedicinesImplantsIcu: Double,
    val consumablesAmount: Double,
    val hasConsumablesRider: Boolean,
    val deductible: Double,
    val coPayPercent: Double
)

data class ClaimEstimateResult(
    val planName: String,
    val sumInsured: Double,
    val totalHospitalBill: Double,
    val proportionateMultiplier: Double,
    val proportionateDeductionAmount: Double,
    val nonPayableConsumablesDeduction: Double,
    val deductibleApplied: Double,
    val coPaymentPercentage: Double,
    val coPaymentDeductionAmount: Double,
    val finalPayableClaimAmount: Double,
    val totalOutOfPocketCost: Double,
    val itemizedNotes: List<String>,
    val citations: List<Citation>
)

data class GrievanceViolation(
    val clause: String,
    val circularRef: String,
    val finding: String
)

data class GrievanceAuditResult(
    val circularRef: String,
    val isIllegal: Boolean,
    val violations: List<GrievanceViolation>,
    val ombudsmanPenaltyInr: Int,
    val escalationPath: List<String>,
    val groEmailDraft: String,
    val citations: List<Citation>
)
