package dev.zedlink.app

object ElicitationForm {
    fun value(field: NativeElicitationField, values: Map<String, String>): String =
        values[field.id] ?: if (field.type == "array") field.defaultArray.orEmpty().joinToString(", ")
        else field.defaultValue ?: if (field.required) field.choices.firstOrNull().orEmpty() else ""
    fun content(fields: List<NativeElicitationField>, values: Map<String, String>, selections: Map<String, Set<String>>): Map<String, Any> {
        val result = mutableMapOf<String, Any>()
        fields.forEach { field ->
            fun invalid(message: String): Nothing = throw IllegalArgumentException("${field.title}: $message")
            val raw = value(field, values)
            val text = raw.trim()
            when (field.type) {
                "boolean" -> if (field.id in values || field.defaultValue != null || field.required) result[field.id] = raw == "true"
                "array" -> {
                    val array = if (field.choices.isNotEmpty()) (selections[field.id] ?: field.defaultArray.orEmpty().toSet()).sorted()
                        else if (field.id !in values && field.defaultArray != null) field.defaultArray
                        else raw.split(',').map(String::trim).filter(String::isNotEmpty)
                    if (field.required && array.isEmpty()) invalid("select or enter at least one value.")
                    if (field.choices.isNotEmpty() && array.any { it !in field.choices }) invalid("select an advertised option.")
                    if (array.isNotEmpty() || field.id in values || field.id in selections || field.defaultArray != null) result[field.id] = array
                }
                else -> {
                    if (text.isEmpty()) { if (field.required) invalid("this field is required."); return@forEach }
                    if (field.choices.isNotEmpty() && raw !in field.choices) invalid("select an advertised option.")
                    when (field.type) {
                        "integer", "number" -> {
                            val number = text.toDoubleOrNull()?.takeIf { it.isFinite() } ?: invalid("enter a finite number.")
                            if (field.minimum != null && number < field.minimum) invalid("minimum is ${field.minimum}.")
                            if (field.maximum != null && number > field.maximum) invalid("maximum is ${field.maximum}.")
                            result[field.id] = if (field.type == "integer") text.toLongOrNull() ?: invalid("enter a whole number.") else number
                        }
                        "string" -> {
                            val length = raw.codePointCount(0, raw.length)
                            if (field.minLength != null && length < field.minLength) invalid("enter at least ${field.minLength} characters.")
                            if (field.maxLength != null && length > field.maxLength) invalid("use at most ${field.maxLength} characters.")
                            result[field.id] = raw
                        }
                        else -> invalid("this input type must be handled in desktop Zed.")
                    }
                }
            }
        }
        return result
    }
}
