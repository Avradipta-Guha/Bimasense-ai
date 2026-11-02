package com.bimasense.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.bimasense.ai.presentation.navigation.BimaSenseNavGraph
import com.bimasense.ai.presentation.theme.BimaSenseTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * Main Activity hosting the Jetpack Compose UI and Hilt Dependency Graph.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BimaSenseTheme {
                BimaSenseNavGraph()
            }
        }
    }
}
