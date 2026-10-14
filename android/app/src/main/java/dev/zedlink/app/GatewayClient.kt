package dev.zedlink.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.UUID
import java.io.ByteArrayOutputStream
import okhttp3.*

class GatewayException(message: String) : IOException(message)

class GatewayClient(private val profile: ConnectionProfile, private val token: String?, private val targetId: String? = null) {
    private val origin = profile.endpoint.trimEnd('/')

    suspend fun gatewayId(): String = request("/v1/gateway").getString("gateway_id")

    suspend fun verifyIdentity() {
        if (!gatewayId().equals(profile.gatewayId, ignoreCase = true)) throw GatewayException("Gateway identity changed. Pair this address again.")
    }

    suspend fun pair(code: String, deviceName: String): Pair<String, String> {
        verifyIdentity()
        val body = JSONObject().put("code", code).put("device_name", deviceName)
        val result = request("/v1/pair", body)
        if (!result.optString("gateway_id").equals(profile.gatewayId, ignoreCase = true)) throw GatewayException("Pairing identity did not match.")
        val nextToken = result.optString("token")
        if (!nextToken.matches(Regex("[0-9a-f]{64}"))) throw GatewayException("Gateway returned an invalid credential.")
        return result.getString("device_id") to nextToken
    }

    suspend fun rpc(method: String, params: JSONObject = JSONObject(), requestId: String = UUID.randomUUID().toString()): JSONObject {
        verifyIdentity()
        val body = JSONObject()
            .put("version", 1)
            .put("request_id", requestId)
            .put("method", method)
            .put("params", params)
        if (method != "instance.list" && targetId != null) body.put("target_id", targetId)
        val envelope = request("/v1/rpc", body, authorized = true)
        if (envelope.optInt("version") != 1 || envelope.optString("request_id") != requestId) {
            throw GatewayException("Gateway response did not match this request.")
        }
        envelope.optJSONObject("error")?.let { throw GatewayException(apiMessage(it.optString("code"))) }
        return envelope.optJSONObject("result") ?: throw GatewayException("Gateway response was incomplete.")
    }

    fun eventStream(threadId: String, afterSequence: Int, onEvent: (JSONObject) -> Unit, onFailure: (Throwable) -> Unit): WebSocket {
        val credential = token ?: throw GatewayException("Pair this device first.")
        val base = URI(origin)
        val target = targetId?.let { "&target_id=${java.net.URLEncoder.encode(it, "UTF-8")}" }.orEmpty()
        val url = "wss://${base.rawAuthority}/v1/events?thread_id=${java.net.URLEncoder.encode(threadId, "UTF-8")}&after_sequence=$afterSequence$target"
        val request = Request.Builder().url(url).header("Sec-WebSocket-Protocol", "zedlink-v1, zedlink-token-$credential").build()
        val completed = java.util.concurrent.atomic.AtomicBoolean(false)
        fun failed(error: Throwable) { if (completed.compareAndSet(false, true)) onFailure(error) }
        return socketClient.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching {
                    val envelope = JSONObject(text)
                    envelope.optJSONObject("error")?.let { throw GatewayException(apiMessage(it.optString("code"))) }
                    envelope.optJSONObject("result") ?: throw GatewayException("Gateway returned an invalid live update.")
                }.onSuccess(onEvent).onFailure(::failed)
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { failed(GatewayException("Live connection closed. Reconnecting.")) }
            override fun onFailure(webSocket: WebSocket, throwable: Throwable, response: Response?) = failed(throwable)
        })
    }

    private suspend fun request(path: String, body: JSONObject? = null, authorized: Boolean = false): JSONObject = withContext(Dispatchers.IO) {
        ConnectionLinks.endpoint(origin)
        val url = URL(origin + path)
        if (url.protocol != "https") throw GatewayException("ZedLink requires a trusted HTTPS address.")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = 10_000
            readTimeout = 20_000
            requestMethod = if (body == null) "GET" else "POST"
            setRequestProperty("Accept", "application/json")
            if (body != null) setRequestProperty("Content-Type", "application/json")
            if (authorized) {
                val credential = token ?: throw GatewayException("Pair this device first.")
                setRequestProperty("Authorization", "Bearer $credential")
            }
            doOutput = body != null
        }
        var phase = "connect"
        var submissionStarted = false
        try {
            // Keep connect/write inside the cleanup boundary, including timeouts.
            connection.connect()
            if (body != null) {
                phase = "send"
                connection.outputStream.use {
                    submissionStarted = true
                    it.write(body.toString().toByteArray(Charsets.UTF_8))
                }
            }
            phase = "response"
            val status = connection.responseCode
            if (status in 300..399) throw GatewayException("Gateway redirects are not allowed.")
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (output.size() <= 1_048_576) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: ByteArray(0)
            if (bytes.size > 1_048_576) throw GatewayException("Gateway response was too large.")
            val objectValue = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }
                .getOrElse { throw GatewayException("Gateway returned an invalid response.") }
            if (status !in 200..299) throw GatewayException(apiMessage(objectValue.optString("error", "HTTP $status")))
            objectValue
        } catch (error: java.net.SocketTimeoutException) {
            val operation = when (path) { "/v1/gateway" -> "discovery"; "/v1/pair" -> "pairing"; else -> "request" }
            throw GatewayTimeoutException(operation, phase, submissionStarted).apply { initCause(error) }
        } finally { connection.disconnect() }
    }

    companion object {
        private val socketClient = OkHttpClient()

        fun profileFromPairingLink(text: String): Pair<ConnectionProfile, String?> = ConnectionLinks.parse(text)

        private fun apiMessage(code: String): String = when (code) {
            "UNAUTHENTICATED" -> "Device credential was revoked. Pair again."
            "THREAD_NOT_EXPOSED" -> "This thread is no longer exposed in desktop Zed."
            "INSTANCE_UNAVAILABLE" -> "Desktop Zed is unavailable."
            "RESYNC_REQUIRED" -> "Native event history changed; refreshing the conversation."
            "UNSUPPORTED_CAPABILITY" -> "This operation is unavailable in the current Zed build."
            else -> code.ifBlank { "Gateway request failed." }
        }
    }
}
