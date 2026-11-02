package com.bimasense.ai.domain.usecase

import com.bimasense.ai.data.repository.BimaSenseRepository
import com.bimasense.ai.domain.model.ClaimEstimateInput
import com.bimasense.ai.domain.model.ClaimEstimateResult
import com.bimasense.ai.domain.model.ComparisonRow
import com.bimasense.ai.domain.model.GrievanceAuditResult
import com.bimasense.ai.domain.model.PolicySummary
import com.bimasense.ai.domain.model.SseStreamEvent
import kotlinx.coroutines.flow.Flow
import java.io.File
import javax.inject.Inject

/**
 * Clean Architecture Use Cases for BimaSense AI (Milestone 5).
 */

class GetPoliciesUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    suspend operator fun invoke(userId: String = "global"): Result<List<PolicySummary>> =
        repository.getPolicies(userId)
}

class UploadPolicyPdfUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    suspend operator fun invoke(
        pdfFile: File,
        insurerName: String,
        planName: String,
        userId: String
    ): Result<PolicySummary> = repository.uploadPolicyPdf(pdfFile, insurerName, planName, userId)
}

class AskPolicyStreamUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    operator fun invoke(
        query: String,
        selectedPlan: String?,
        userId: String = "global"
    ): Flow<SseStreamEvent> = repository.streamPolicyChat(query, selectedPlan, userId)
}

class ComparePlansUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    suspend operator fun invoke(
        planA: String,
        planB: String,
        criteria: List<String>
    ): Result<Pair<String, List<ComparisonRow>>> = repository.comparePlans(planA, planB, criteria)
}

class CalculateClaimUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    suspend operator fun invoke(input: ClaimEstimateInput): Result<ClaimEstimateResult> =
        repository.estimateClaim(input)
}

class VerifyGrievanceUseCase @Inject constructor(
    private val repository: BimaSenseRepository
) {
    suspend operator fun invoke(
        insurerName: String,
        planName: String,
        continuousMonths: Int,
        rejectionReason: String,
        dischargeWaitHours: Double?,
        rejectedByTpaDirectly: Boolean,
        ombudsmanOverdueDays: Int?
    ): Result<GrievanceAuditResult> = repository.verifyGrievance(
        insurerName = insurerName,
        planName = planName,
        continuousMonths = continuousMonths,
        rejectionReason = rejectionReason,
        dischargeWaitHours = dischargeWaitHours,
        rejectedByTpaDirectly = rejectedByTpaDirectly,
        ombudsmanOverdueDays = ombudsmanOverdueDays
    )
}
