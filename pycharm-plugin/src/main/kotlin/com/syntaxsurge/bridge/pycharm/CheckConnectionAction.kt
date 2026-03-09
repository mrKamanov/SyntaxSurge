package com.syntaxsurge.bridge.pycharm

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project

class CheckConnectionAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project: Project? = e.project
        if (project == null) {
            showNotification(project, "Откройте файл в редакторе.", NotificationType.WARNING)
            return
        }
        val payload = EditorContext.fromProject(project)
        if (payload == null) {
            showNotification(project, "SyntaxSurge Bridge: откройте файл в редакторе.", NotificationType.WARNING)
            return
        }
        BridgeClient.checkConnection(payload)
            .onSuccess { msg -> showNotification(project, "SyntaxSurge Bridge: $msg", NotificationType.INFORMATION) }
            .onFailure { ex -> showNotification(project, "SyntaxSurge Bridge: ${ex.message}", NotificationType.ERROR) }
    }

    private fun showNotification(project: Project?, message: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("SyntaxSurge Bridge")
            ?.createNotification(message, type)
            ?.notify(project)
    }
}
