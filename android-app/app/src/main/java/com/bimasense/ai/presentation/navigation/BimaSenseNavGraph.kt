package com.bimasense.ai.presentation.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Calculate
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.CompareArrows
import androidx.compose.material.icons.filled.FolderSpecial
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bimasense.ai.presentation.screens.agent_scanner.HospitalBillScannerScreen
import com.bimasense.ai.presentation.screens.calculator.ClaimCalculatorScreen
import com.bimasense.ai.presentation.screens.chat.ChatScreen
import com.bimasense.ai.presentation.screens.compare.PlanComparatorScreen
import com.bimasense.ai.presentation.screens.grievance.GrievanceHelperScreen
import com.bimasense.ai.presentation.screens.vault.PolicyVaultScreen

/**
 * Jetpack Compose Navigation Graph & Bottom Navigation Bar connecting all 6 screens
 * (including Milestone 7's CameraX Hospital Bill Scanner Agent).
 */

sealed class ScreenRoute(val route: String, val label: String, val icon: ImageVector) {
    data object Vault : ScreenRoute("vault", "Vault", Icons.Default.FolderSpecial)
    data object Chat : ScreenRoute("chat", "Copilot", Icons.Default.Chat)
    data object Compare : ScreenRoute("compare", "Compare", Icons.Default.CompareArrows)
    data object Calculator : ScreenRoute("calculator", "Calc", Icons.Default.Calculate)
    data object BillScanner : ScreenRoute("scanner", "Bill OCR", Icons.Default.ReceiptLong)
    data object Grievance : ScreenRoute("grievance", "IRDAI", Icons.Default.Gavel)
}

@Composable
fun BimaSenseNavGraph() {
    val navController = rememberNavController()
    val tabs = listOf(
        ScreenRoute.Vault,
        ScreenRoute.Chat,
        ScreenRoute.Compare,
        ScreenRoute.Calculator,
        ScreenRoute.BillScanner,
        ScreenRoute.Grievance
    )

    Scaffold(
        bottomBar = {
            NavigationBar {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentRoute = navBackStackEntry?.destination?.route

                tabs.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        onClick = {
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) }
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = ScreenRoute.Vault.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(ScreenRoute.Vault.route) {
                PolicyVaultScreen(
                    onOpenChatWithPlan = {
                        navController.navigate(ScreenRoute.Chat.route)
                    }
                )
            }
            composable(ScreenRoute.Chat.route) {
                ChatScreen()
            }
            composable(ScreenRoute.Compare.route) {
                PlanComparatorScreen()
            }
            composable(ScreenRoute.Calculator.route) {
                ClaimCalculatorScreen()
            }
            composable(ScreenRoute.BillScanner.route) {
                HospitalBillScannerScreen()
            }
            composable(ScreenRoute.Grievance.route) {
                GrievanceHelperScreen()
            }
        }
    }
}
