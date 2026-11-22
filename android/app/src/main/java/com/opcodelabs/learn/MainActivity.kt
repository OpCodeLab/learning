package com.opcodelabs.learn

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.opcodelabs.learn.ui.CourseScreen
import com.opcodelabs.learn.ui.CoursesScreen
import com.opcodelabs.learn.ui.LearnTheme
import com.opcodelabs.learn.ui.LoginScreen
import com.opcodelabs.learn.ui.PlayerScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // No screenshots or screen recordings of the app (videos show black in recordings).
        // Debug builds (never given to students) allow screenshots for testing.
        if (!BuildConfig.DEBUG) {
            window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        }
        // Every screen has a black bar at the top (like the website): light status-bar icons.
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        val app = application as LearnApp

        setContent {
            LearnTheme {
                val nav = rememberNavController()
                var notice by remember { mutableStateOf<String?>(null) }
                val signedOut: (String?) -> Unit = { msg ->
                    app.session.token = null
                    notice = msg
                    nav.navigate("login") { popUpTo(0) }
                }
                NavHost(nav, startDestination = if (app.session.token != null) "courses" else "login") {
                    composable("login") {
                        LoginScreen(app.api, app.session.email, notice) {
                            notice = null
                            nav.navigate("courses") { popUpTo(0) }
                        }
                    }
                    composable("courses") {
                        CoursesScreen(app.api, app.session.email.orEmpty(), { slug -> nav.navigate("course/$slug") }, signedOut)
                    }
                    composable("course/{slug}") { e ->
                        val slug = e.arguments?.getString("slug")!!
                        CourseScreen(app.api, slug, { nav.popBackStack() }, { lid -> nav.navigate("player/$slug/$lid") }, signedOut)
                    }
                    composable("player/{slug}/{lid}") { e ->
                        PlayerScreen(app.api, e.arguments?.getString("slug")!!, e.arguments?.getString("lid")!!,
                            { nav.popBackStack() }, signedOut)
                    }
                }
            }
        }
    }
}
