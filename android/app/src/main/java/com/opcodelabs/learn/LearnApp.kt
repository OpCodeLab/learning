package com.opcodelabs.learn

import android.app.Application
import com.opcodelabs.learn.data.Api
import com.opcodelabs.learn.data.Session

class LearnApp : Application() {
    lateinit var session: Session
        private set
    lateinit var api: Api
        private set

    override fun onCreate() {
        super.onCreate()
        session = Session(this)
        api = Api(session)
    }
}
