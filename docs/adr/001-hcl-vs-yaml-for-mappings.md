# ADR 001: HCL vs YAML for Module Dependency Mappings

## Status
Proposed

## Context
We need to define module dependencies and their input/output mappings for the TIM (Terraform IBM Modules) MCP server. The mappings file describes how outputs from source modules connect to inputs of target modules. We need to choose between HCL (HashiCorp Configuration Language) and YAML for this configuration format.

## Decision Drivers
- **Terraform Ecosystem Alignment**: Consistency with Terraform's native configuration language
- **Readability**: Ease of understanding for developers and operators
- **Tooling Support**: Availability of parsers, validators, and IDE support
- **Expressiveness**: Ability to represent complex relationships and logic
- **Maintainability**: Ease of updates and version control
- **Community Familiarity**: Developer experience with the format

## Options Considered

### Option 1: HCL (HashiCorp Configuration Language)

#### Advantages
- **Native Terraform Format**: HCL is Terraform's native configuration language, providing natural alignment
- **Rich Tooling**: Extensive tooling support including `terraform fmt`, `terraform validate`, and IDE plugins
- **Type Safety**: Built-in type system with validation capabilities
- **Expressions**: Supports complex expressions, functions, and interpolations
- **Comments**: Supports both single-line (`//`, `#`) and multi-line (`/* */`) comments
- **Terraform Community**: Familiar to all Terraform users and developers
- **Consistency**: Maintains consistency with Terraform module structure

#### Disadvantages
- **Learning Curve**: Requires understanding HCL syntax for non-Terraform users
- **Parsing Complexity**: Requires HCL parser library (e.g., `python-hcl2`)
- **Less Universal**: Not as widely used outside HashiCorp ecosystem

#### Example
```hcl
# mappings.hcl
metadata {
  name   = "terraform-ibm-key-protect"
  source = "terraform-ibm-modules/terraform-ibm-key-protect"
}

compatible_module "resource_group" {
  source = "terraform-ibm-modules/resource-group"
}

compatible_variables {
  resource_group_id   = "resource_group.output.resource_group_id"
}
```

### Option 2: YAML (YAML Ain't Markup Language)

#### Advantages
- **Universal Format**: Widely used across many tools and platforms
- **Simple Syntax**: Easy to read and write with minimal syntax
- **Broad Tooling**: Extensive parser support in all programming languages
- **Human-Friendly**: Very readable with minimal punctuation
- **Schema Validation**: JSON Schema support for validation
- **Wide Adoption**: Familiar to developers from various backgrounds

#### Disadvantages
- **Not Terraform Native**: Requires translation layer for Terraform concepts
- **Indentation Sensitivity**: Whitespace-dependent syntax can cause errors
- **Limited Expressions**: No native support for complex expressions or functions
- **Type Ambiguity**: Can have issues with type inference (e.g., `yes/no` vs booleans)
- **Inconsistency**: Different from Terraform's native configuration approach

#### Example
```yaml
# mappings.yaml
metadata:
  name: terraform-ibm-key-protect
  source: terraform-ibm-modules/terraform-ibm-key-protect

compatible_modules:
  - name: resource_group
    source: terraform-ibm-modules/resource-group

compatible_variables:
  resource_group_id: resource_group.output.resource_group_id
```

## Decision
**We choose HCL (HashiCorp Configuration Language)** for the module dependency mappings file.

## Rationale

1. **Terraform Ecosystem Alignment**: Since we're working exclusively with Terraform IBM Modules, using HCL maintains consistency with the Terraform ecosystem and reduces cognitive load for developers already familiar with Terraform.

2. **Native Tooling**: HCL provides access to Terraform's native tooling (`terraform fmt`, `terraform validate`) which can be leveraged for validation and formatting of mappings files.

3. **Type Safety**: HCL's type system provides better validation and error detection at parse time, reducing runtime errors.

4. **Future Extensibility**: HCL's support for expressions and functions provides flexibility for future enhancements, such as conditional dependencies or computed values.

5. **Community Expectations**: Terraform module developers expect HCL format, making adoption and contribution easier.

6. **Consistency**: Using HCL for mappings maintains consistency with Terraform module structure, making it easier to understand the relationship between modules and their dependencies.

## Consequences

### Positive
- Seamless integration with Terraform tooling and workflows
- Better type safety and validation capabilities
- Familiar syntax for Terraform developers
- Potential for advanced features using HCL expressions
- Consistent with Terraform module ecosystem

### Negative
- Requires HCL parser library in Python (`python-hcl2`)
- Less familiar to developers outside Terraform ecosystem
- Slightly more complex syntax compared to YAML

### Neutral
- Need to document HCL syntax for contributors unfamiliar with it
- May need to provide examples and templates for common patterns

## Implementation Notes

1. **Parser**: Use `python-hcl2` library for parsing HCL files in Python
2. **Validation**: Implement schema validation for the mappings structure
3. **Documentation**: Provide clear examples and templates in the repository
4. **Tooling**: Document how to use `terraform fmt` for formatting mappings files
5. **Migration**: If migrating from YAML, provide conversion scripts

## References
- [HCL Specification](https://github.com/hashicorp/hcl/blob/main/hclsyntax/spec.md)
- [Terraform Configuration Language](https://www.terraform.io/language)
- [python-hcl2 Library](https://github.com/amplify-education/python-hcl2)
- [YAML Specification](https://yaml.org/spec/)

## Related Decisions
- ADR 002: Module Dependency Schema Structure (future)
- ADR 003: Validation Strategy for Mappings (future)

