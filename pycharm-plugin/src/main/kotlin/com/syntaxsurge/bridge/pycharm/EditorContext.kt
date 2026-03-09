package com.syntaxsurge.bridge.pycharm

import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.fileTypes.FileTypeManager

/** Собирает из текущего редактора payload для моста (line, column, строки, язык, расширение). */
object EditorContext {

    fun fromEditor(editor: Editor?, project: Project?): BridgeClient.Payload? {
        if (editor == null || project == null) return null
        val document = editor.document
        val caret = editor.caretModel.primaryCaret
        val offset = caret.offset
        val lineCount = document.lineCount
        if (lineCount == 0) return null
        val lineIndex = document.getLineNumber(offset).coerceIn(0, lineCount - 1)
        val lineStart = document.getLineStartOffset(lineIndex)
        val lineEnd = document.getLineEndOffset(lineIndex)
        val lineContent = document.getText(com.intellij.openapi.util.TextRange(lineStart, lineEnd))
        val lineAbove = if (lineIndex > 0) {
            val s = document.getLineStartOffset(lineIndex - 1)
            val e = document.getLineEndOffset(lineIndex - 1)
            document.getText(com.intellij.openapi.util.TextRange(s, e))
        } else ""
        val lineBelow = if (lineIndex < lineCount - 1) {
            val s = document.getLineStartOffset(lineIndex + 1)
            val e = document.getLineEndOffset(lineIndex + 1)
            document.getText(com.intellij.openapi.util.TextRange(s, e))
        } else ""
        val col0 = offset - lineStart
        val line1Based = lineIndex + 1
        val col1Based = (col0 + 1).coerceAtLeast(1)
        val (languageId, fileExtension) = getLanguageAndExtension(editor)
        return BridgeClient.Payload(
            line = line1Based,
            column = col1Based,
            lineContent = lineContent,
            lineAbove = lineAbove,
            lineBelow = lineBelow,
            languageId = languageId,
            fileExtension = fileExtension
        )
    }

    fun fromProject(project: Project): BridgeClient.Payload? {
        val editor = FileEditorManager.getInstance(project).selectedTextEditor ?: return null
        return fromEditor(editor, project)
    }

    private fun getLanguageAndExtension(editor: Editor): Pair<String, String> {
        val file: VirtualFile? = FileDocumentManager.getInstance().getFile(editor.document)
        val extVal = file?.extension
        val ext = when {
            extVal != null -> ".${extVal.lowercase()}"
            else -> ""
        }
        val langId = when {
            file != null -> {
                val fileType = FileTypeManager.getInstance().getFileTypeByFile(file)
                fileType.name.lowercase().ifEmpty { ext.removePrefix(".").ifEmpty { "" } }
            }
            else -> ext.removePrefix(".").ifEmpty { "" }
        }
        return (langId.ifEmpty { ext.removePrefix(".") }) to ext
    }
}
