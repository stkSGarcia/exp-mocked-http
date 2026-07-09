## ADDED Requirements

### Requirement: Reusable Template Definitions
The system SHALL load `Template` definitions as named reusable template fragments.

#### Scenario: Template is registered by key
- **WHEN** a loaded definition has `kind` set to `Template` with a non-empty `key` and string `template`
- **THEN** the system SHALL register the template source under that key for later template rendering

#### Scenario: Template is not included in behavior matching
- **WHEN** a loaded definition has `kind` set to `Template`
- **THEN** the system SHALL NOT include that definition in the effective behavior list used for HTTP request matching

#### Scenario: Template rejects behavior fields
- **WHEN** a loaded `Template` definition includes `expect`, `actions`, `values`, or `extend`
- **THEN** the system SHALL reject that definition as invalid

### Requirement: Abstract Behavior Definitions
The system SHALL load `AbstractBehavior` definitions as reusable behavior bases that never trigger directly.

#### Scenario: Abstract behavior accepts reusable behavior fields
- **WHEN** a loaded definition has `kind` set to `AbstractBehavior` with `expect`, `actions`, or `values`
- **THEN** the system SHALL accept those fields for inheritance by concrete behaviors

#### Scenario: Abstract behavior is not matched directly
- **WHEN** a loaded definition has `kind` set to `AbstractBehavior`
- **THEN** the system SHALL NOT include that definition in the effective behavior list used for HTTP request matching

#### Scenario: Abstract behavior rejects unsupported fields
- **WHEN** a loaded `AbstractBehavior` definition includes `extend` or `template`
- **THEN** the system SHALL reject that definition as invalid

### Requirement: Behavior Inheritance
The system SHALL allow a concrete `Behavior` to extend another `Behavior` or an `AbstractBehavior`.

#### Scenario: Parent is resolved regardless of definition order
- **WHEN** a `Behavior` extends a parent key that is defined later in the discovered YAML stream
- **THEN** the system SHALL resolve the parent and load the child using inherited fields

#### Scenario: Missing parent extension is skipped
- **WHEN** a `Behavior` extends a parent key that is not present
- **THEN** the system SHALL validate and load the child using only its own fields

#### Scenario: Missing inherited requirements still fail
- **WHEN** a `Behavior` extends a missing parent and the child does not define required concrete behavior fields
- **THEN** the system SHALL reject the child as invalid

#### Scenario: Values maps are merged with child override
- **WHEN** a child behavior extends a parent and both define `values`
- **THEN** the effective behavior SHALL contain the merged values map with child keys overriding matching parent keys

#### Scenario: Parent actions precede child actions before ordering
- **WHEN** a child behavior extends a parent and both define `actions`
- **THEN** the effective behavior SHALL include the parent's actions before the child's actions before action order sorting is applied

#### Scenario: Expect maps are merged recursively
- **WHEN** a child behavior extends a parent and both define nested `expect` fields
- **THEN** the effective behavior SHALL inherit missing child fields and override matching parent fields with child values

#### Scenario: Other fields prefer child non-zero values
- **WHEN** a child behavior extends a parent and both define scalar fields such as `kind` or `key`
- **THEN** the effective behavior SHALL use the child value when it is present and non-zero, otherwise the parent value

#### Scenario: Inheritance cycles are rejected
- **WHEN** resolving a behavior extension would revisit the same definition key in the parent chain
- **THEN** the system SHALL reject the definition as invalid

### Requirement: Definition Values
The system SHALL allow concrete and abstract behavior definitions to define arbitrary `values` maps.

#### Scenario: Behavior values map is accepted
- **WHEN** a `Behavior` definition includes `values` as a mapping
- **THEN** the system SHALL store that mapping on the effective behavior

#### Scenario: Abstract behavior values map is accepted
- **WHEN** an `AbstractBehavior` definition includes `values` as a mapping
- **THEN** the system SHALL make that mapping available to child behaviors through inheritance

#### Scenario: Non-map values are rejected
- **WHEN** a `Behavior` or `AbstractBehavior` definition includes `values` that is not a mapping
- **THEN** the system SHALL reject that definition as invalid

## MODIFIED Requirements

### Requirement: Behavior Schema Validation
The system SHALL validate loaded mock definitions before serving requests.

#### Scenario: Missing key is rejected
- **WHEN** a loaded definition omits `key`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Empty key is rejected
- **WHEN** a loaded definition has `key` set to an empty string or non-string value
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Kind defaults to Behavior
- **WHEN** a loaded definition omits `kind`
- **THEN** the system SHALL treat `kind` as `Behavior`

#### Scenario: Valid kinds are accepted
- **WHEN** a loaded definition has `kind` set to `Behavior`, `Template`, or `AbstractBehavior`
- **THEN** the system SHALL validate that definition using the field rules for that kind

#### Scenario: Invalid kind is rejected
- **WHEN** a loaded definition has `kind` set to any value other than `Behavior`, `Template`, or `AbstractBehavior`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Behavior allowed fields are enforced
- **WHEN** a loaded `Behavior` definition includes fields outside `key`, `kind`, `extend`, `expect`, `actions`, or `values`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Behavior template field is rejected
- **WHEN** a loaded `Behavior` definition includes `template`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Template allowed fields are enforced
- **WHEN** a loaded `Template` definition includes fields outside `key`, `kind`, or `template`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Abstract behavior allowed fields are enforced
- **WHEN** a loaded `AbstractBehavior` definition includes fields outside `key`, `kind`, `expect`, `actions`, or `values`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Multiple HTTP replies are rejected
- **WHEN** an effective concrete behavior contains more than one `reply_http` action after inheritance is resolved
- **THEN** the system SHALL reject that behavior as invalid
