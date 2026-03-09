package com.syntaxsurge.bridge.pycharm

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.editor.event.CaretEvent
import com.intellij.openapi.editor.event.CaretListener
import com.intellij.openapi.fileEditor.FileEditorManagerEvent
import com.intellij.openapi.fileEditor.FileEditorManagerListener
import com.intellij.openapi.fileEditor.TextEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

/** Подписывается на смену редактора и движение курсора, отправляет контекст на мост. */
class SyntaxSurgeBridgeStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        val connection = project.messageBus.connect()
        connection.subscribe(FileEditorManagerListener.FILE_EDITOR_MANAGER, object : FileEditorManagerListener {
            override fun selectionChanged(event: FileEditorManagerEvent) {
                sendCurrentContext(project)
                (event.newEditor as? TextEditor)?.editor?.let { editor ->
                    editor.caretModel.addCaretListener(caretListener(project, editor))
                }
            }
        })
        ApplicationManager.getApplication().invokeLater {
            val editor = com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).selectedTextEditor
            if (editor != null) {
                sendCurrentContext(project)
                editor.caretModel.addCaretListener(caretListener(project, editor))
            }
        }
    }

    private fun caretListener(project: Project, editor: com.intellij.openapi.editor.Editor): CaretListener {
        return object : CaretListener {
            override fun caretPositionChanged(e: CaretEvent) {
                EditorContext.fromEditor(editor, project)?.let { BridgeClient.send(it) }
            }
        }
    }

    private fun sendCurrentContext(project: Project) {
        EditorContext.fromProject(project)?.let { BridgeClient.send(it) }
    }
}
