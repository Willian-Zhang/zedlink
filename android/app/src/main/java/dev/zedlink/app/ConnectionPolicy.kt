package dev.zedlink.app

import java.net.URI
import java.util.UUID

/** Safe request metadata only; never includes the URL, body, token or one-use code. */
class GatewayTimeoutException(val operation: String, val phase: String, val resultMayBeUnknown: Boolean) :
    java.net.SocketTimeoutException("Gateway timed out")

/** No credentials or pairing code are retained by these diagnostics. */
fun connectionFailure(error: Throwable): String = when (error) {
    is GatewayTimeoutException -> {
        val stage = if (error.phase == "connect") "while connecting" else if (error.phase == "send") "while sending the request" else "while waiting for the response"
        when (error.operation) {
            "discovery" -> "HTTPS gateway check timed out $stage. No pairing request was sent. Open the same HTTPS address in Chrome or Termux and check the VPN route and gateway port."
            "pairing" -> if (error.resultMayBeUnknown)
                "Pairing timed out $stage after submission began. The result may be unknown; check paired devices on the host before creating a fresh pairing code. Do not retry automatically."
                else "Pairing connection timed out $stage. No pairing request was sent. Check the private route and gateway service."
            else -> "Gateway request timed out $stage. Check the private route and gateway service. Check any pending operation before retrying."
        }
    }
    is javax.net.ssl.SSLException -> "HTTPS identity could not be verified. Check the hostname and certificate."
    is java.net.UnknownHostException -> "Hostname lookup failed. Check the saved address and VPN DNS route."
    is java.net.SocketTimeoutException -> "Gateway connection timed out. Check the private route, HTTPS address and gateway port."
    is java.net.ConnectException -> "Gateway cannot be reached. Check the private route and gateway service."
    else -> error.message ?: "Connection failed."
}

object ConnectionLinks {
    fun endpoint(value: String): URI {
        val uri = URI(value.trim())
        require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
            (uri.path.isNullOrEmpty() || uri.path == "/") && (uri.port == -1 || uri.port in 1..65535)) {
            "Use the gateway's HTTPS address without credentials, query, fragment or a path prefix."
        }
        return uri
    }
    fun parse(value: String): Pair<ConnectionProfile, String?> {
        require(value.length <= 4096) { "Pairing link is too long." }
        val uri = URI(value.trim())
        val appLink = uri.scheme == "zedlink"
        if (appLink) require(uri.host == "pair" && uri.rawUserInfo == null && uri.port == -1 &&
            uri.rawFragment == null && uri.path.isNullOrEmpty()) { "Use a ZedLink pairing link." }
        val rows = (if (appLink) uri.rawQuery else uri.rawFragment).orEmpty().split('&').map {
            val parts = it.split('=', limit = 2)
            require(parts.size == 2) { "Pairing link is incomplete." }
            java.net.URLDecoder.decode(parts[0], "UTF-8") to java.net.URLDecoder.decode(parts[1], "UTF-8")
        }
        require(rows.map { it.first }.distinct().size == rows.size) { "Pairing link contains duplicate fields." }
        val allFields = rows.toMap()
        val address = if (appLink) requireNotNull(allFields["endpoint"]) { "Pairing address is missing." } else value.trim().substringBefore('#')
        val fields = if (appLink) allFields - "endpoint" else allFields
        require(fields.keys == setOf("gateway") || fields.keys == setOf("v", "gateway", "pair")) { "Use the workstation's ZedLink pairing link." }
        val gateway = fields.getValue("gateway").lowercase()
        require(UUID.fromString(gateway).toString() == gateway) { "Pairing link has an invalid gateway identity." }
        val code = fields["pair"]
        require(code == null || fields["v"] == "1" && code.length == 10 && code.all { it in '0'..'9' }) { "Pairing link has an invalid code or version." }
        endpoint(address)
        return ConnectionProfile("Desktop", address.trimEnd('/'), gateway) to code
    }
}

object ConnectionProfiles {
    fun profileForSave(profile: ConnectionProfile, profiles: List<ConnectionProfile>): ConnectionProfile {
        val existing = profiles.firstOrNull { it.id == profile.id ||
            (it.gatewayId.equals(profile.gatewayId, true) && it.endpoint.trimEnd('/').equals(profile.endpoint.trimEnd('/'), true)) }
        return profile.copy(id = existing?.id ?: profile.id)
    }
}

/** Persisted conversation drafts belong to a gateway and workspace, across route/epoch changes. */
fun draftStorageKey(gateway: String?, target: String?, thread: String?): String? {
    if (gateway.isNullOrBlank() || target.isNullOrBlank() || thread.isNullOrBlank()) return null
    val fields = listOf(gateway.lowercase(), target, thread)
    val material = fields.joinToString("") { "${it.length}:$it" }
    val digest = java.security.MessageDigest.getInstance("SHA-256").digest(material.toByteArray(Charsets.UTF_8))
    return "draft.v2." + digest.joinToString("") { "%02x".format(it.toInt() and 255) }
}
