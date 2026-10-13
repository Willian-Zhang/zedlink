package dev.zedlink.app

import org.junit.Assert.*
import org.junit.Test

class ConnectionPolicyTest {
    private val gateway = java.util.UUID.nameUUIDFromBytes("zedlink-pairing-fixture".toByteArray()).toString()
    private fun rejects(value: String) {
        try { ConnectionLinks.parse(value); fail("Unsafe pairing link accepted") } catch (_: IllegalArgumentException) { }
    }
    @Test fun loadsPairingAndAlreadyPairedLinksWithoutLosingIdentity() {
        val (profile, code) = ConnectionLinks.parse("https://desktop.example:44679/#v=1&gateway=$gateway&pair=0123456789")
        assertEquals("https://desktop.example:44679", profile.endpoint)
        assertEquals(gateway, profile.gatewayId)
        assertEquals("0123456789", code)
        assertNull(ConnectionLinks.parse("https://[fd00::1]/#gateway=$gateway").second)
    }
    @Test fun rejectsCredentialInjectionAndAmbiguousLinkFields() {
        listOf("http://desktop/#gateway=$gateway", "https://user:secret@desktop/#gateway=$gateway",
            "https://desktop/?token=secret#gateway=$gateway", "https://desktop/prefix#gateway=$gateway",
            "https://desktop/#gateway=$gateway&gateway=$gateway", "https://desktop/#gateway=$gateway&extra=value",
            "https://desktop/#v=2&gateway=$gateway&pair=0123456789", "https://desktop/#v=1&gateway=$gateway&pair=٠١٢٣٤٥٦٧٨٩",
            "https://desktop/#gateway=1-1-1-1-1", "https://desktop:0/#gateway=$gateway").forEach(::rejects)
    }
    @Test fun differentRoutesKeepTheirIdentityAndEditsReuseTheSavedIdentity() {
        val first = ConnectionProfile("Tailnet", "https://desktop.example", gateway, "first", "Tailscale")
        val second = ConnectionProfile("LAN", "https://desktop.lan", gateway, "second", "Local HTTPS")
        assertEquals("second", ConnectionProfiles.profileForSave(second, listOf(first)).id)
        assertEquals("first", ConnectionProfiles.profileForSave(first.copy(endpoint = "https://new.example"), listOf(first, second)).id)
        assertEquals("first", ConnectionProfiles.profileForSave(first.copy(id = "fresh", endpoint = first.endpoint + "/"), listOf(first, second)).id)
    }
    @Test fun networkFailuresDoNotClaimTheVpnIsDisabledOrZedIsDown() {
        assertTrue(connectionFailure(java.net.UnknownHostException()).contains("Hostname lookup"))
        assertTrue(connectionFailure(javax.net.ssl.SSLException("fixture")).contains("identity"))
        assertTrue(connectionFailure(java.net.SocketTimeoutException()).contains("unknown"))
    }
}
