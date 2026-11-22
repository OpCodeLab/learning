package com.opcodelabs.learn.data

import kotlinx.serialization.Serializable

// Mirrors app/learn/api.py on the server.

@Serializable
data class User(val email: String, val name: String = "", val is_admin: Boolean = false)

@Serializable
data class LoginResponse(val token: String, val user: User)

@Serializable
data class Me(val email: String, val name: String = "", val is_admin: Boolean = false,
              val max_devices: Int = 2, val device: String = "")

@Serializable
data class CourseCard(
    val slug: String, val title: String, val description: String = "", val cover: String? = null,
    val lessons: Int = 0, val done: Int = 0, val pct: Int = 0, val expires: Long? = null,
)

@Serializable
data class CourseList(val courses: List<CourseCard>)

@Serializable
data class Attachment(val id: String, val name: String, val size: Long = 0)

@Serializable
data class Lesson(
    val id: String, val title: String, val number: Int? = null, val index: Int = 0,
    val completed: Boolean = false, val position: Double = 0.0, val duration: Double = 0.0,
    val attachments: List<Attachment> = emptyList(),
)

@Serializable
data class Section(val title: String, val lessons: List<Lesson>, val resources: List<Attachment> = emptyList())

@Serializable
data class Course(
    val slug: String, val title: String, val description: String = "", val cover: String? = null,
    val done: Int = 0, val lessons: Int = 0, val pct: Int = 0, val resume: String? = null,
    val watermark: String? = null, val sections: List<Section>,
) {
    val allLessons: List<Lesson> get() = sections.flatMap { it.lessons }
    fun sectionOf(lessonId: String): Section? = sections.firstOrNull { s -> s.lessons.any { it.id == lessonId } }
}

@Serializable
data class PlayStatus(val elsewhere: String? = null)

@Serializable
data class AppVersion(val version_code: Int = 0, val version_name: String = "", val url: String = "",
                      val sha256: String = "", val size: Long = 0)
