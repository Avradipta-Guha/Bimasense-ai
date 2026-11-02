package com.bimasense.ai.data.remote

import com.google.gson.annotations.SerializedName
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

/**
 * Retrofit API Contract matching the FastAPI Backend (`Milestone 4`).
 */
interface BimaSenseApiService {

    @GET("api/v1/policies/list")
    suspend fun listPolicies(
        @Query("user_id") userId: String = "global"
    ): PolicyListDto

    @Multipart
    @POST("api/v1/policies/upload")
    suspend fun uploadPolicyPdf(
        @Part file: MultipartBody.Part,
        @Part("insurer_name") insurerName: RequestBody,
        @Part("plan_name") planName: RequestBody,
        @Part("user_id") userId: RequestBody
    ): PolicyUploadResponseDto

    @Streaming
    @GET("api/v1/policies/{policy_id}/pdf")
    suspend fun downloadPolicyPdf(
        @Path("policy_id") policyId: String
    ): ResponseBody

    @POST("api/v1/chat/query")
    suspend fun queryChatSync(
        @Body request: ChatRequestDto
    ): ChatResponseDto

    @POST("api/v1/compare")
    suspend fun comparePlans(
        @Body request: ComparePlansRequestDto
    ): ComparePlansResponseDto

    @POST("api/v1/calculator/estimate")
    suspend fun estimateClaim(
        @Body request: ClaimEstimateRequestDto
    ): ClaimEstimateResponseDto

    @POST("api/v1/grievance/verify")
    suspend fun verifyGrievance(
        @Body request: GrievanceVerifyRequestDto
    ): GrievanceVerifyResponseDto
}

// ==============================================================================
// Data Transfer Objects (DTOs) matching FastAPI `app/schemas/api_models.py`
// ==============================================================================

data class PolicySummaryDto(
    @SerializedName("policy_id") val policyId: String,
    @SerializedName("insurer_name") val insurerName: String,
    @SerializedName("plan_name") val planName: String,
    @SerializedName("uin") val uin: String = "",
    @SerializedName("sum_insured_options") val sumInsuredOptions: List<String> = emptyList(),
    @SerializedName("room_rent_rule") val roomRentRule: String,
    @SerializedName("ped_waiting_period") val pedWaitingPeriod: String,
    @SerializedName("restoration_rule") val restorationRule: String,
    @SerializedName("consumables_coverage") val consumablesCoverage: String,
    @SerializedName("co_payment_rule") val coPaymentRule: String,
    @SerializedName("is_user_uploaded") val isUserUploaded: Boolean = false,
    @SerializedName("file_name") val fileName: String = "",
    @SerializedName("total_pages") val totalPages: Int = 1
)

data class PolicyListDto(
    @SerializedName("total_count") val totalCount: Int,
    @SerializedName("policies") val policies: List<PolicySummaryDto>
)

data class PolicyUploadResponseDto(
    @SerializedName("status") val status: String,
    @SerializedName("policy_id") val policyId: String,
    @SerializedName("insurer_name") val insurerName: String,
    @SerializedName("plan_name") val planName: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("file_name") val fileName: String,
    @SerializedName("pages_parsed") val pagesParsed: Int,
    @SerializedName("tables_extracted") val tablesExtracted: Int,
    @SerializedName("chunks_indexed") val chunksIndexed: Int
)

data class CitationDto(
    @SerializedName("source_title") val sourceTitle: String,
    @SerializedName("page_number") val pageNumber: Int,
    @SerializedName("section_heading") val sectionHeading: String = "",
    @SerializedName("section_category") val sectionCategory: String = "",
    @SerializedName("snippet") val snippet: String,
    @SerializedName("relevance_score") val relevanceScore: Float = 1.0f
)

data class ComparisonMetricRowDto(
    @SerializedName("criterion") val criterion: String,
    @SerializedName("plan_a_value") val planAValue: String,
    @SerializedName("plan_b_value") val planBValue: String,
    @SerializedName("winner_or_verdict") val winnerOrVerdict: String = ""
)

data class ChatRequestDto(
    @SerializedName("query") val query: String,
    @SerializedName("user_id") val userId: String = "global",
    @SerializedName("selected_plan") val selectedPlan: String? = null,
    @SerializedName("compare_plans") val comparePlans: List<String> = emptyList()
)

data class ChatResponseDto(
    @SerializedName("intent") val intent: String,
    @SerializedName("answer_markdown") val answerMarkdown: String,
    @SerializedName("citations") val citations: List<CitationDto> = emptyList(),
    @SerializedName("comparison_table") val comparisonTable: List<ComparisonMetricRowDto>? = null,
    @SerializedName("follow_up_suggestions") val followUpSuggestions: List<String> = emptyList(),
    @SerializedName("confidence_score") val confidenceScore: Float = 1.0f
)

data class ComparePlansRequestDto(
    @SerializedName("plan_a") val planA: String,
    @SerializedName("plan_b") val planB: String,
    @SerializedName("criteria") val criteria: List<String>,
    @SerializedName("user_id") val userId: String = "global"
)

data class ComparePlansResponseDto(
    @SerializedName("plan_a") val planA: String,
    @SerializedName("plan_b") val planB: String,
    @SerializedName("summary_markdown") val summaryMarkdown: String,
    @SerializedName("comparison_table") val comparisonTable: List<ComparisonMetricRowDto>,
    @SerializedName("citations") val citations: List<CitationDto> = emptyList()
)

data class ClaimEstimateRequestDto(
    @SerializedName("plan_name") val planName: String,
    @SerializedName("sum_insured") val sumInsured: Double,
    @SerializedName("total_bill") val totalBill: Double,
    @SerializedName("allowed_room_rent") val allowedRoomRent: Double?,
    @SerializedName("actual_room_rent") val actualRoomRent: Double?,
    @SerializedName("associated_medical_expenses") val associatedMedicalExpenses: Double?,
    @SerializedName("exempt_expenses_medicines_implants_icu") val exemptExpensesMedicinesImplantsIcu: Double,
    @SerializedName("consumables_amount") val consumablesAmount: Double,
    @SerializedName("has_consumables_rider") val hasConsumablesRider: Boolean,
    @SerializedName("deductible") val deductible: Double,
    @SerializedName("co_pay_percent") val coPayPercent: Double
)

data class ClaimEstimateResponseDto(
    @SerializedName("plan_name") val planName: String,
    @SerializedName("sum_insured") val sumInsured: Double,
    @SerializedName("total_hospital_bill") val totalHospitalBill: Double,
    @SerializedName("proportionate_multiplier") val proportionateMultiplier: Double,
    @SerializedName("proportionate_deduction_amount") val proportionateDeductionAmount: Double,
    @SerializedName("non_payable_consumables_deduction") val nonPayableConsumablesDeduction: Double,
    @SerializedName("deductible_applied") val deductibleApplied: Double,
    @SerializedName("co_payment_percentage") val coPaymentPercentage: Double,
    @SerializedName("co_payment_deduction_amount") val coPaymentDeductionAmount: Double,
    @SerializedName("final_payable_claim_amount") val finalPayableClaimAmount: Double,
    @SerializedName("total_out_of_pocket_cost") val totalOutOfPocketCost: Double,
    @SerializedName("itemized_notes") val itemizedNotes: List<String>,
    @SerializedName("policy_rule_citations") val policyRuleCitations: List<CitationDto> = emptyList()
)

data class GrievanceVerifyRequestDto(
    @SerializedName("insurer_name") val insurerName: String,
    @SerializedName("plan_name") val planName: String,
    @SerializedName("continuous_policy_months") val continuousPolicyMonths: Int,
    @SerializedName("rejection_reason") val rejectionReason: String,
    @SerializedName("discharge_wait_hours") val dischargeWaitHours: Double? = null,
    @SerializedName("rejected_by_tpa_directly") val rejectedByTpaDirectly: Boolean = false,
    @SerializedName("ombudsman_award_days_overdue") val ombudsmanAwardDaysOverdue: Int? = null
)

data class GrievanceVerifyResponseDto(
    @SerializedName("circular_ref") val circularRef: String,
    @SerializedName("is_rejection_or_action_illegal") val isRejectionOrActionIllegal: Boolean,
    @SerializedName("violations_detected") val violationsDetected: List<Map<String, String>>,
    @SerializedName("ombudsman_penalty_inr") val ombudsmanPenaltyInr: Int,
    @SerializedName("recommended_escalation_path") val recommendedEscalationPath: List<String>,
    @SerializedName("gro_escalation_email_draft") val groEscalationEmailDraft: String,
    @SerializedName("citations") val citations: List<CitationDto> = emptyList()
)
