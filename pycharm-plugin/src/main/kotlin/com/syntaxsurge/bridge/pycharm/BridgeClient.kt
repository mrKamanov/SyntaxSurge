package com.syntaxsurge.bridge.pycharm

import com.intellij.openapi.diagnostic.Logger
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

object BridgeClient {
    private const val BRIDGE_HOST = "127.0.0.1"
    private const val BRIDGE_PORT = 8765
    private const val SOURCE = "pycharm"
    private val LOG = Logger.getInstance(BridgeClient::class.java)

    data class Payload(
        val line: Int,
        val column: Int,
        val lineContent: String,
        val lineAbove: String,
        val lineBelow: String,
        val languageId: String,
        val fileExtension: String
    ) {
        fun toJson(): String {
            return """{"line":$line,"column":$column,"lineContent":${escape(lineContent)},"lineAbove":${escape(lineAbove)},"lineBelow":${escape(lineBelow)},"source":"$SOURCE","languageId":${escape(languageId)},"fileExtension":${escape(fileExtension)}}"""
        }

        private fun escape(s: String): String {
            if (s.isEmpty()) return "\"\""
            val sb = StringBuilder(s.length + 4)
            sb.append('"')
            for (c in s) {
                when (c) {
                    '\\' -> sb.append("\\\\")
                    '"' -> sb.append("\\\"")
                    '\n' -> sb.append("\\n")
                    '\r' -> sb.append("\\r")
                    '\t' -> sb.append("\\t")
                    else -> sb.append(c)
                }
            }
            sb.append('"')
            return sb.toString()
        }
    }

    fun send(payload: Payload): Boolean {
        return try {
            val url = URL("http://$BRIDGE_HOST:$BRIDGE_PORT/cursor")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.connectTimeout = 1500
            conn.readTimeout = 1500
            val body = payload.toJson().toByteArray(StandardCharsets.UTF_8)
            conn.setRequestProperty("Content-Length", body.size.toString())
            OutputStreamWriter(conn.outputStream, StandardCharsets.UTF_8).use { it.write(String(body, StandardCharsets.UTF_8)) }
            val code = conn.responseCode
            if (code != 200) {
                LOG.warn("SyntaxSurge Bridge: ответ $code")
            }
            code == 200
        } catch (e: Exception) {
            LOG.debug("SyntaxSurge Bridge: мост недоступен", e)
            false
        }
    }

    fun checkConnection(payload: Payload): Result<String> {
        return try {
            val url = URL("http://$BRIDGE_HOST:$BRIDGE_PORT/cursor")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.connectTimeout = 2000
            conn.readTimeout = 2000
            val body = payload.toJson().toByteArray(StandardCharsets.UTF_8)
            conn.setRequestProperty("Content-Length", body.size.toString())
            OutputStreamWriter(conn.outputStream, StandardCharsets.UTF_8).use { it.write(String(body, StandardCharsets.UTF_8)) }
            val code = conn.responseCode
            if (code == 200) {
                Result.success("Мост принял данные. Строка ${payload.line}, столбец ${payload.column}.")
            } else {
                Result.failure(Exception("Ответ $code. Запустите gui_typer.py или run.py."))
            }
        } catch (e: Exception) {
            Result.failure(Exception("Не удалось подключиться к мосту ($BRIDGE_HOST:$BRIDGE_PORT). ${e.message}"))
        }
    }
}
