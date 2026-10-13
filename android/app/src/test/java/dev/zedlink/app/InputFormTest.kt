package dev.zedlink.app

import org.junit.Assert.*
import org.junit.Test

class InputFormTest {
    private fun field(type: String = "string", required: Boolean = true, choices: List<String> = emptyList()) =
        NativeElicitationField("value", "Value", type, required, choices)
    private fun submit(field: NativeElicitationField, value: String? = null) =
        ElicitationForm.content(listOf(field), if (value == null) emptyMap() else mapOf("value" to value), emptyMap())
    private fun invalid(field: NativeElicitationField, value: String) {
        assertThrows(IllegalArgumentException::class.java) { submit(field, value) }
    }
    @Test fun submitsUntouchedVisibleChoiceAndSchemaDefault() {
        val choice = field(choices = listOf("local", "remote"))
        assertEquals("local", ElicitationForm.value(choice, emptyMap()))
        assertEquals("local", submit(choice)["value"])
        assertEquals("remote", submit(choice.copy(defaultValue = "remote"))["value"])
        invalid(choice, "unadvertised")
    }
    @Test fun optionalChoiceIsOmittedButRequiredFalseIsAValue() {
        assertTrue(submit(field(required = false, choices = listOf("a"))).isEmpty())
        assertEquals(false, submit(field("boolean"))["value"])
        assertTrue(submit(field("boolean", required = false)).isEmpty())
    }
    @Test fun validatesFiniteNumbersWholeIntegersAndBounds() {
        val number = field("number").copy(minimum = 1.0, maximum = 3.0)
        assertEquals(2.5, submit(number, "2.5")["value"])
        listOf("NaN", "Infinity", "text", "0", "4").forEach { invalid(number, it) }
        assertEquals(2L, submit(field("integer"), "2")["value"])
        invalid(field("integer"), "2.5")
    }
    @Test fun preservesMultipleChoicesAndArrayDefaults() {
        val array = field("array", choices = listOf("a", "b", "c"))
        assertEquals(listOf("a", "c"), ElicitationForm.content(listOf(array), emptyMap(), mapOf("value" to setOf("c", "a")))["value"])
        val default = field("array").copy(defaultArray = listOf("b", "a", "b"))
        assertEquals("b, a, b", ElicitationForm.value(default, emptyMap()))
        assertEquals(listOf("b", "a", "b"), submit(default)["value"])
        assertThrows(IllegalArgumentException::class.java) { submit(array) }
    }
    @Test fun validatesRequiredAndUnicodeLength() {
        invalid(field(), "  ")
        val text = field().copy(minLength = 1, maxLength = 1)
        assertEquals("😀", submit(text, "😀")["value"])
        invalid(text, "ab")
        assertTrue(submit(field(required = false), "").isEmpty())
    }
}
