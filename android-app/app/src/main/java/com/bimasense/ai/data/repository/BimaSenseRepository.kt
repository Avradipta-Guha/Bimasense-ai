package com.bimasense.ai.data.repository

import android.content.Context
import com.bimasense.ai.data.local.ChatHistoryDao
import com.bimasense.ai.data.local.PolicyDao
import com.bimasense.ai.data.local.PolicyEntity
import com.bimasense.ai.data.remote.BimaSenseApiService
import com.bimasense.ai.data.remote.ClaimEstimateRequestDto
import com.bimasense.ai.data.remote.ComparePlansRequestDto
import com.bimasense.ai.data.remote.GrievanceVerifyRequestDto
import com.bimasense.ai.data.remote.SseChatClient
import com.bimasense.ai.domain.model.Citation
import com.bimasense.ai.domain.model.ClaimEstimateInput
import com.bimasense.ai.domain.model.ClaimEstimateResult
import com.bimasense.ai.domain.model.ComparisonRow
import com.bimasense.ai.domain.model.GrievanceAuditResult
import com.bimasense.ai.domain.model.GrievanceViolation
import com.bimasense.ai.domain.model.PolicySummary
import com.bimasense.ai.domain.model.SseStreamEvent
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Clean Architecture Repository coordinating Remote FastAPI + SSE calls
 * with Room Local Database offline caching and PDF file storage.
 */
@Singleton
class BimaSenseRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val apiService: BimaSenseApiService,
    private val sseChatClient: SseChatClient,
    private val policyDao: PolicyDao,
    private val chatHistoryDao: ChatHistoryDao
) {

    suspend fun getPolicies(userId: String = "global"): Result<List<PolicySummary>> =
        withContext(Dispatchers.IO) {
            try {
                val dto = apiService.listPolicies(userId)
                val entities = dto.policies.map { p ->
                    PolicyEntity(
                        policyId = p.policyId,
                        insurerName = p.insurerName,
                        planName = p.planName,
                        uin = p.uin,
                        sumInsuredOptionsCsv = p.sumInsuredOptions.joinToString(","),
                        roomRentRule = p.roomRentRule,
                        pedWaitingPeriod = p.pedWaitingPeriod,
                        restorationRule = p.restorationRule,
                        consumablesCoverage = p.consumablesCoverage,
                        coPaymentRule = p.coPaymentRule,
                        isUserUploaded = p.isUserUploaded,
                        fileName = p.fileName,
                        totalPages = p.totalPages
                    )
                }
                policyDao.insertPolicies(entities)
                Result.success(entities.map { it.toDomain() })
            } catch (e: Exception) {
                val cached = policyDao.getAllPolicies().map { it.toDomain() }
                if (cached.isNotEmpty()) {
                    Result.success(cached)
                } else {
                    Result.failure(e)
                }
            }
        }

    suspend fun uploadPolicyPdf(
        pdfFile: File,
        insurerName: String,
        planName: String,
        userId: String
    ): Result<PolicySummary> = withContext(Dispatchers.IO) {
        try {
            val reqFile = pdfFile.asRequestBody("application/pdf".toMediaTypeOrNull())
            val bodyPart = MultipartBody.Part.createFormData("file", pdfFile.name, reqFile)
            val insurerPart = insurerName.toRequestBody("text/plain".toMediaTypeOrNull())
            val planPart = planName.toRequestBody("text/plain".toMediaTypeOrNull())
            val userPart = userId.toRequestBody("text/plain".toMediaTypeOrNull())

            val resp = apiService.uploadPolicyPdf(bodyPart, insurerPart, planPart, userPart)
            val summary = PolicySummary(
                policyId = resp.policyId,
                insurerName = resp.insurerName,
                planName = resp.planName,
                uin = "USER-UPLOADED",
                sumInsuredOptions = listOf("As per Policy Schedule"),
                roomRentRule = "Indexed (${resp.chunksIndexed} clauses, ${resp.tablesExtracted} tables)",
                pedWaitingPeriod = "Indexed from ${resp.fileName}",
                restorationRule = "Indexed from ${resp.fileName}",
                consumablesCoverage = "Indexed from ${resp.fileName}",
                coPaymentRule = "Indexed from ${resp.fileName}",
                isUserUploaded = true,
                fileName = resp.fileName,
                totalPages = resp.pagesParsed
            )
            Result.success(summary)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getOrDownloadPolicyPdf(policyId: String, fileName: String): Result<File> =
        withContext(Dispatchers.IO) {
            try {
                val pdfCacheDir = File(context.cacheDir, "policy_pdfs").apply { mkdirs() }
                val targetFile = File(pdfCacheDir, fileName.ifBlank { "$policyId.pdf" })
                if (targetFile.exists() && targetFile.length() > 100) {
                    return@withContext Result.success(targetFile)
                }
                val body = apiService.downloadPolicyPdf(policyId)
                targetFile.outputStream().use { out ->
                    body.byteStream().copyTo(out)
                }
                Result.success(targetFile)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    fun streamPolicyChat(
        query: String,
        selectedPlan: String?,
        userId: String = "global"
    ): Flow<SseStreamEvent> = sseChatClient.streamChat(query, selectedPlan, userId)

    suspend fun comparePlans(
        planA: String,
        planB: String,
        criteria: List<String>
    ): Result<Pair<String, List<ComparisonRow>>> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.comparePlans(
                ComparePlansRequestDto(
                    planA = planA,
                    planB = planB,
                    criteria = criteria
                )
            )
            val rows = resp.comparisonTable.map {
                ComparisonRow(
                    criterion = it.criterion,
                    planAValue = it.planAValue,
                    planBValue = it.planBValue,
                    verdict = it.winnerOrVerdict
                )
            }
            Result.success(resp.summaryMarkdown to rows)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun estimateClaim(input: ClaimEstimateInput): Result<ClaimEstimateResult> =
        withContext(Dispatchers.IO) {
            try {
                val resp = apiService.estimateClaim(
                    ClaimEstimateRequestDto(
                        planName = input.planName,
                        sumInsured = input.sumInsured,
                        totalBill = input.totalBill,
                        allowedRoomRent = input.allowedRoomRent,
                        actualRoomRent = input.actualRoomRent,
                        associatedMedicalExpenses = input.associatedMedicalExpenses,
                        exemptExpensesMedicinesImplantsIcu = input.exemptExpensesMedicinesImplantsIcu,
                        consumablesAmount = input.consumablesAmount,
                        hasConsumablesRider = input.hasConsumablesRider,
                        deductible = input.deductible,
                        coPayPercent = input.coPayPercent
                    )
                )
                Result.success(
                    ClaimEstimateResult(
                        planName = resp.planName,
                        sumInsured = resp.sumInsured,
                        totalHospitalBill = resp.totalHospitalBill,
                        proportionateMultiplier = resp.proportionateMultiplier,
                        proportionateDeductionAmount = resp.proportionateDeductionAmount,
                        nonPayableConsumablesDeduction = resp.nonPayableConsumablesDeduction,
                        deductibleApplied = resp.deductibleApplied,
                        coPaymentPercentage = resp.coPaymentPercentage,
                        coPaymentDeductionAmount = resp.coPaymentDeductionAmount,
                        finalPayableClaimAmount = resp.finalPayableClaimAmount,
                        totalOutOfPocketCost = resp.totalOutOfPocketCost,
                        itemizedNotes = resp.itemizedNotes,
                        citations = resp.policyRuleCitations.map {
                            Citation(
                                sourceTitle = it.sourceTitle,
                                pageNumber = it.pageNumber,
                                sectionHeading = it.sectionHeading,
                                sectionCategory = it.sectionCategory,
                                snippet = it.snippet,
                                relevanceScore = it.relevanceScore
                            )
                        }
                    )
                )
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun verifyGrievance(
        insurerName: String,
        planName: String,
        continuousMonths: Int,
        rejectionReason: String,
        dischargeWaitHours: Double?,
        rejectedByTpaDirectly: Boolean,
        ombudsmanOverdueDays: Int?
    ): Result<GrievanceAuditResult> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.verifyGrievance(
                GrievanceVerifyRequestDto(
                    insurerName = insurerName,
                    planName = planName,
                    continuousPolicyMonths = continuousMonths,
                    rejectionReason = rejectionReason,
                    dischargeWaitHours = dischargeWaitHours,
                    rejectedByTpaDirectly = rejectedByTpaDirectly,
                    ombudsmanAwardDaysOverdue = ombudsmanOverdueDays
                )
            )
            Result.success(
                GrievanceAuditResult(
                    circularRef = resp.circularRef,
                    isIllegal = resp.isRejectionOrActionIllegal,
                    violations = resp.violationsDetected.map {
                        GrievanceViolation(
                            clause = it["clause"] ?: "",
                            circularRef = it["circular_ref"] ?: "",
                            finding = it["finding"] ?: ""
                        )
                    },
                    ombudsmanPenaltyInr = resp.ombudsmanPenaltyInr,
                    escalationPath = resp.recommendedEscalationPath,
                    groEmailDraft = resp.groEscalationEmailDraft,
                    citations = resp.citations.map {
                        Citation(
                            sourceTitle = it.sourceTitle,
                            pageNumber = it.pageNumber,
                            sectionHeading = it.sectionHeading,
                            sectionCategory = it.sectionCategory,
                            snippet = it.snippet,
                            relevanceScore = it.relevanceScore
                        )
                    }
                )
            )
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun PolicyEntity.toDomain(): PolicySummary = PolicySummary(
        policyId = policyId,
        insurerName = insurerName,
        planName = planName,
        uin = uin,
        sumInsuredOptions = sumInsuredOptionsCsv.split(",").filter { it.isNotBlank() },
        roomRentRule = roomRentRule,
        pedWaitingPeriod = pedWaitingPeriod,
        restorationRule = restorationRule,
        consumablesCoverage = consumablesCoverage,
        coPaymentRule = coPaymentRule,
        isUserUploaded = isUserUploaded,
        fileName = fileName,
        totalPages = totalPages
    )
}
