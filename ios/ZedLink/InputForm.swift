import Foundation

enum ElicitationForm {
    static func value(_ field: NativeElicitationField, values: [String: String]) -> String {
        if let value = values[field.id] { return value }
        if field.type == "array" { return arrayValues(field).joined(separator: ", ") }
        return field.defaultValue ?? (field.required ? field.choices.first ?? "" : "")
    }
    private static func arrayValues(_ field: NativeElicitationField) -> [String] {
        guard let text = field.defaultValue, let data = text.data(using: .utf8),
              let values = try? JSONDecoder().decode([String].self, from: data) else { return [] }
        return values
    }
    static func arrayDefault(_ field: NativeElicitationField) -> Set<String> { Set(arrayValues(field)) }
    static func content(_ fields: [NativeElicitationField], values: [String: String], selections: [String: Set<String>]) throws -> [String: Any] {
        var result: [String: Any] = [:]
        for field in fields {
            let raw = value(field, values: values), trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            func fail(_ message: String) throws -> Never { throw GatewayFailure.native("\(field.title): \(message)") }
            if field.type == "boolean" {
                if values[field.id] != nil || field.defaultValue != nil || field.required { result[field.id] = raw == "true" }
                continue
            }
            if field.type == "array" {
                let array = !field.choices.isEmpty ? (selections[field.id] ?? arrayDefault(field)).sorted()
                    : (values[field.id] == nil && field.defaultValue != nil ? arrayValues(field)
                       : raw.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })
                if field.required && array.isEmpty { try fail("select or enter at least one value.") }
                if !field.choices.isEmpty && array.contains(where: { !field.choices.contains($0) }) { try fail("select an advertised option.") }
                if !array.isEmpty || selections[field.id] != nil || values[field.id] != nil || field.defaultValue != nil { result[field.id] = array }
                continue
            }
            if trimmed.isEmpty {
                if field.required { try fail("this field is required.") }
                continue
            }
            if !field.choices.isEmpty && !field.choices.contains(raw) { try fail("select an advertised option.") }
            switch field.type {
            case "integer", "number":
                guard let number = Double(trimmed), number.isFinite else { try fail("enter a finite number.") }
                if let min = field.minimum, number < min { try fail("minimum is \(min).") }
                if let max = field.maximum, number > max { try fail("maximum is \(max).") }
                if field.type == "integer" {
                    guard let integer = Int(trimmed) else { try fail("enter a whole number.") }
                    result[field.id] = integer
                } else { result[field.id] = number }
            case "string":
                if let min = field.minLength, raw.unicodeScalars.count < min { try fail("enter at least \(min) characters.") }
                if let max = field.maxLength, raw.unicodeScalars.count > max { try fail("use at most \(max) characters.") }
                result[field.id] = raw
            default: try fail("this input type must be handled in desktop Zed.")
            }
        }
        return result
    }
}
