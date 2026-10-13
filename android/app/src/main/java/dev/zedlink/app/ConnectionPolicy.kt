package dev.zedlink.app

import java.net.URI
import java.util.UUID

/** No credentials or pairing code are retained by these diagnostics. */
fun connectionFailure(error: Throwable): String = when (error) {
    is javax.net.ssl.SSLException -> "HTTPS identity could not be verified. Check the hostname and certificate."
    is java.net.UnknownHostException -> "Hostname lookup failed. Check the saved address and VPN DNS route."
    is java.net.SocketTimeoutException -> "Gateway timed out. Check the private route and gateway service. A pending pairing result may be unknown; do not retry automatically."
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
        val uri = URI(value.trim())
        val rows = uri.rawFragment.orEmpty().split('&').map {
            val parts = it.split('=', limit = 2)
            require(parts.size == 2) { "Pairing link is incomplete." }
            java.net.URLDecoder.decode(parts[0], "UTF-8") to java.net.URLDecoder.decode(parts[1], "UTF-8")
        }
        require(rows.map { it.first }.distinct().size == rows.size) { "Pairing link contains duplicate fields." }
        val fields = rows.toMap()
        require(fields.keys == setOf("gateway") || fields.keys == setOf("v", "gateway", "pair")) { "Use the workstation's ZedLink pairing link." }
        val gateway = fields.getValue("gateway").lowercase()
        require(UUID.fromString(gateway).toString() == gateway) { "Pairing link has an invalid gateway identity." }
        val code = fields["pair"]
        require(code == null || fields["v"] == "1" && code.length == 10 && code.all { it in '0'..'9' }) { "Pairing link has an invalid code or version." }
        val address = value.trim().substringBefore('#')
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
