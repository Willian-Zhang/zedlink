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
    @Test fun appLinksRequireAnExplicitVerifiedHttpsDestination() {
        val (profile, code) = ConnectionLinks.parse("zedlink://pair?endpoint=https%3A%2F%2Fdesktop.example%3A44679&v=1&gateway=$gateway&pair=0123456789")
        assertEquals("https://desktop.example:44679", profile.endpoint)
        assertEquals("0123456789", code)
        listOf("zedlink://pair?endpoint=http%3A%2F%2Fdesktop&gateway=$gateway",
            "zedlink://notification?endpoint=https%3A%2F%2Fdesktop&gateway=$gateway",
            "zedlink://pair/path?endpoint=https%3A%2F%2Fdesktop&gateway=$gateway",
            "zedlink://pair?endpoint=https%3A%2F%2Fdesktop&gateway=$gateway&endpoint=https%3A%2F%2Fother",
            "zedlink://pair?endpoint=https%3A%2F%2Fdesktop&gateway=$gateway&secret=anything").forEach(::rejects)
    }
    @Test fun differentRoutesKeepTheirIdentityAndEditsReuseTheSavedIdentity() {
        val first = ConnectionProfile("Tailnet", "https://desktop.example", gateway, "first", "Tailscale")
        val second = ConnectionProfile("LAN", "https://desktop.lan", gateway, "second", "Local HTTPS")
        assertEquals("second", ConnectionProfiles.profileForSave(second, listOf(first)).id)
        assertEquals("first", ConnectionProfiles.profileForSave(first.copy(endpoint = "https://new.example"), listOf(first, second)).id)
        assertEquals("first", ConnectionProfiles.profileForSave(first.copy(id = "fresh", endpoint = first.endpoint + "/"), listOf(first, second)).id)
    }
    @Test fun draftKeysKeepGatewayAndWorkspaceBoundaries() {
        assertEquals(draftStorageKey("GATEWAY", "workspace", "thread"), draftStorageKey("gateway", "workspace", "thread"))
        assertNotEquals(draftStorageKey("gateway", "first", "thread"), draftStorageKey("gateway", "second", "thread"))
        assertNotEquals(draftStorageKey("first", "workspace", "thread"), draftStorageKey("second", "workspace", "thread"))
        assertNotEquals(draftStorageKey("gateway", "a:b", "c"), draftStorageKey("gateway", "a", "b:c"))
        assertNull(draftStorageKey("gateway", null, "thread"))
    }
    @Test fun networkFailuresDoNotClaimTheVpnIsDisabledOrZedIsDown() {
        assertTrue(connectionFailure(java.net.UnknownHostException()).contains("Hostname lookup"))
        assertTrue(connectionFailure(javax.net.ssl.SSLException("fixture")).contains("identity"))
        assertFalse(connectionFailure(java.net.SocketTimeoutException()).contains("pairing result"))
    }
    @Test fun discoveryTimeoutNeverClaimsPairingWasSubmitted() {
        for (phase in listOf("connect", "response")) {
            val message = connectionFailure(GatewayTimeoutException("discovery", phase, false))
            assertTrue(message.contains("HTTPS gateway check"))
            assertTrue(message.contains("No pairing request was sent"))
            assertFalse(message.contains("unknown"))
        }
    }
    @Test fun pairingTimeoutDistinguishesConnectFailureFromUnknownSubmission() {
        assertTrue(connectionFailure(GatewayTimeoutException("pairing", "connect", false)).contains("No pairing request was sent"))
        val submitted = connectionFailure(GatewayTimeoutException("pairing", "response", true))
        assertTrue(submitted.contains("unknown"))
        assertTrue(submitted.contains("Do not retry automatically"))
        assertFalse(submitted.contains("No pairing request was sent"))
    }

}
