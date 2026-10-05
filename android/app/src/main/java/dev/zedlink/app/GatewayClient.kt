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

class GatewayException(message: String) : IOException(message)

class GatewayClient(private val profile: ConnectionProfile, private val token: String?) {
    private val origin = profile.endpoint.trimEnd('/')

    suspend fun gatewayId(): String = request("/v1/gateway").getString("gateway_id")

    suspend fun verifyIdentity() {
        if (gatewayId() != profile.gatewayId) throw GatewayException("Gateway identity changed. Pair this address again.")
    }

    suspend fun pair(code: String, deviceName: String): Pair<String, String> {
        verifyIdentity()
        val body = JSONObject().put("code", code).put("device_name", deviceName)
        val result = request("/v1/pair", body)
        if (result.optString("gateway_id") != profile.gatewayId) throw GatewayException("Pairing identity did not match.")
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
        val envelope = request("/v1/rpc", body, authorized = true)
        if (envelope.optInt("version") != 1 || envelope.optString("request_id") != requestId) {
            throw GatewayException("Gateway response did not match this request.")
        }
        envelope.optJSONObject("error")?.let { throw GatewayException(apiMessage(it.optString("code"))) }
        return envelope.optJSONObject("result") ?: throw GatewayException("Gateway response was incomplete.")
    }

    private suspend fun request(path: String, body: JSONObject? = null, authorized: Boolean = false): JSONObject = withContext(Dispatchers.IO) {
        val url = URL(origin + path)
        if (url.protocol != "https") throw@withContext GatewayException("ZedLink requires a trusted HTTPS address.")
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
            if (body != null) {
                doOutput = true
                outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
        }
        try {
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
        } finally { connection.disconnect() }
    }

    companion object {
        fun profileFromPairingLink(text: String): Pair<ConnectionProfile, String?> {
            val uri = URI(text.trim())
            if (uri.scheme != "https" || uri.host.isNullOrBlank()) throw GatewayException("Paste the trusted HTTPS pairing link.")
            val fragment = uri.rawFragment.orEmpty().split('&').mapNotNull {
                val parts = it.split('=', limit = 2)
                if (parts.size == 2) java.net.URLDecoder.decode(parts[0], "UTF-8") to java.net.URLDecoder.decode(parts[1], "UTF-8") else null
            }.toMap()
            val gateway = fragment["gateway"].orEmpty()
            if (gateway.isBlank()) throw GatewayException("Pairing link has no gateway identity.")
            val port = if (uri.port == -1) "" else ":${uri.port}"
            return ConnectionProfile("My Zed", "https://${uri.host}$port", gateway) to fragment["pair"]
        }

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
